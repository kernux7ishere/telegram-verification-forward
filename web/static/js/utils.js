/* Small helpers shared by the dashboard scripts. */
(function (global) {
  'use strict';

  var STORAGE_PREFIX = 'tvf:';

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function toNumber(value, fallback) {
    var n = Number(value);
    return Number.isFinite(n) ? n : (fallback === undefined ? 0 : fallback);
  }

  /* 1047 -> "1,047" */
  function number(value) {
    return toNumber(value).toLocaleString('en-US', { maximumFractionDigits: 0 });
  }

  function decimal(value, digits) {
    var places = digits === undefined ? 1 : digits;
    return toNumber(value).toFixed(places);
  }

  /* ISO timestamp -> "2 mins ago" */
  function timeAgo(iso) {
    if (!iso) return 'never';
    var then = Date.parse(iso);
    if (Number.isNaN(then)) return 'unknown';

    var seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 0) seconds = 0;
    if (seconds < 10) return 'just now';
    if (seconds < 60) return seconds + 's ago';

    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + (minutes === 1 ? ' min ago' : ' mins ago');

    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + (hours === 1 ? ' hour ago' : ' hours ago');

    var days = Math.floor(hours / 24);
    return days + (days === 1 ? ' day ago' : ' days ago');
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait);
    };
  }

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  /* localStorage that never throws (private mode, quota, disabled storage). */
  var storage = {
    get: function (key, fallback) {
      try {
        var raw = global.localStorage.getItem(STORAGE_PREFIX + key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (err) {
        return fallback;
      }
    },
    set: function (key, value) {
      try {
        global.localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
        return true;
      } catch (err) {
        return false;
      }
    }
  };

  global.Utils = {
    clamp: clamp,
    toNumber: toNumber,
    number: number,
    decimal: decimal,
    timeAgo: timeAgo,
    debounce: debounce,
    randomBetween: randomBetween,
    storage: storage
  };
})(window);
