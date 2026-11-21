/* WebSocket 客户端：封装连接、自动重连、操作请求、事件订阅。
   所有前端请求都通过此模块发送，替代原先的 fetch / api() 调用。 */

(function () {
  'use strict';

  // ---- 单例 ----
  var _instance = null;

  function getWS() {
    if (!_instance) {
      _instance = new WSClient();
    }
    return _instance;
  }

  // ---- WSClient ----
  function WSClient() {
    this._ws = null;
    this._connected = false;
    this._authenticated = false;
    this._pending = new Map();       // msg_id -> {resolve, reject}
    this._handlers = {};             // event_name -> [fn]
    this._opHandlers = {};           // op_name -> [fn]（后端推来的事件）
    this._offlineQueue = [];         // 断线时缓存的操作
    this._reconnectDelay = 1000;
    this._reconnectTimer = null;
    this._authToken = '';
    this._closed = false;

    // 从 cookie 读取 agents_token（登录时由后端 set_cookie）
    var m = document.cookie.match(/agents_token=([^;]+)/);
    if (m) this._authToken = m[1];
  }

  WSClient.prototype.connect = function () {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) return;
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = proto + '//' + location.host + '/ws';
    var self = this;

    try {
      this._ws = new WebSocket(url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }

    this._ws.onopen = function () {
      self._connected = true;
      self._reconnectDelay = 1000;
      // 发认证帧
      if (self._authToken) {
        self._sendRaw({ op: 'auth', token: self._authToken });
      } else {
        // 无 token（auth 关闭时）也发 auth，后端会直接通过
        self._sendRaw({ op: 'auth', token: '' });
      }
      // 补发离线队列
      self._flushOfflineQueue();
      self._emit('connected');
    };

    this._ws.onmessage = function (ev) {
      var data;
      try { data = JSON.parse(ev.data); } catch (e) { return; }
      self._onMessage(data);
    };

    this._ws.onclose = function () {
      self._connected = false;
      self._authenticated = false;
      self._emit('disconnected');
      if (!self._closed) self._scheduleReconnect();
    };

    this._ws.onerror = function () {
      // onclose 会随后触发，无需额外处理
    };
  };

  WSClient.prototype.close = function () {
    this._closed = true;
    if (this._reconnectTimer) { clearTimeout(this._reconnectTimer); this._reconnectTimer = null; }
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._connected = false;
  };

  WSClient.prototype._scheduleReconnect = function () {
    if (this._closed) return;
    var self = this;
    var delay = Math.min(this._reconnectDelay, 30000);
    this._reconnectDelay = Math.min(this._reconnectDelay * 2, 30000);
    this._reconnectTimer = setTimeout(function () {
      self._reconnectTimer = null;
      self.connect();
    }, delay);
  };

  WSClient.prototype._sendRaw = function (obj) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(obj));
    }
  };

  WSClient.prototype._onMessage = function (data) {
    var op = data.op || '';
    var self = this;

    // 认证结果
    if (op === 'auth_result') {
      this._authenticated = data.ok;
      if (data.ok) {
        // 重连后发 resync
        this._sendRaw({ op: 'resync', last_event_id: '' });
      }
      this._emit('auth_result', data);
      return;
    }

    // 心跳
    if (op === 'pong') {
      this._emit('pong', data);
      return;
    }

    // 操作响应
    if (op === 'ack' || op === 'error') {
      var msgId = data.msg_id || '';
      var entry = this._pending.get(msgId);
      if (entry) {
        this._pending.delete(msgId);
        if (op === 'ack') {
          entry.resolve(data.data || {});
        } else {
          entry.reject(new Error(data.detail || '操作失败'));
        }
      }
      this._emit('op_result', data);
      return;
    }

    // 重连回放
    if (op === 'reconnect') {
      this._emit('reconnect', data);
      return;
    }

    // 事件流（chat_event / config.changed / question.answered 等）
    // 统一格式: {event: "..."} 或 {op: "..."}
    if (data.event) {
      this._emit('chat_event', data);
      this._emit(data.event, data);
    } else if (data.op && !this._opHandlers[data.op]) {
      // 未知 op 也广播
      this._emit('push', data);
    } else if (data.op) {
      var fns = this._opHandlers[data.op];
      if (fns) fns.forEach(function (fn) { fn(data); });
    }
  };

  /**
   * 发送操作请求，返回 Promise（resolve 时返回 data）。
   * 断线时请求进入离线队列，重连后自动补发。
   */
  WSClient.prototype.call = function (opName, data) {
    var self = this;
    var msgId = 'm_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    var frame = { op: opName, msg_id: msgId, data: data || {} };

    return new Promise(function (resolve, reject) {
      if (!self._connected || !self._ws || self._ws.readyState !== WebSocket.OPEN) {
        self._offlineQueue.push({ frame: frame, resolve: resolve, reject: reject });
        return;
      }
      self._pending.set(msgId, { resolve: resolve, reject: reject });
      self._sendRaw(frame);
      // 超时保护（120s）
      setTimeout(function () {
        if (self._pending.has(msgId)) {
          self._pending.delete(msgId);
          reject(new Error('请求超时: ' + opName));
        }
      }, 120000);
    });
  };

  WSClient.prototype._flushOfflineQueue = function () {
    var queue = this._offlineQueue;
    this._offlineQueue = [];
    var self = this;
    queue.forEach(function (item) {
      var msgId = item.frame.msg_id;
      self._pending.set(msgId, { resolve: item.resolve, reject: item.reject });
      self._sendRaw(item.frame);
      setTimeout(function () {
        if (self._pending.has(msgId)) {
          self._pending.delete(msgId);
          item.reject(new Error('请求超时（补发后）: ' + item.frame.op));
        }
      }, 120000);
    });
  };

  // ---- 事件订阅 ----
  WSClient.prototype.on = function (event, fn) {
    if (!this._handlers[event]) this._handlers[event] = [];
    this._handlers[event].push(fn);
    return this;
  };

  WSClient.prototype.off = function (event, fn) {
    var list = this._handlers[event];
    if (!list) return;
    var idx = list.indexOf(fn);
    if (idx >= 0) list.splice(idx, 1);
    return this;
  };

  WSClient.prototype._emit = function (event, data) {
    var list = this._handlers[event];
    if (list) list.forEach(function (fn) { fn(data); });
  };

  // ---- 便捷方法 ----
  var ws = getWS();
  ws.connect();
  window.ws = ws;

})();
