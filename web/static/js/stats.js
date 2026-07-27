/* Alpine component: polls /api/stats and keeps the dashboard in sync. */
(function (global) {
  'use strict';

  var BASE_INTERVAL = 1000;      // spec: refresh every 1 second
  var MAX_INTERVAL = 60000;      // backoff ceiling after repeated failures
  var REQUEST_TIMEOUT = 8000;
  var CACHE_KEY = 'stats-cache';

  // Only what the dashboard renders. /api/stats returns more (code counts,
  // bot status); those fields are deliberately not surfaced here.
  var EMPTY_STATS = {
    memory_used_mb: 0,
    memory_percent: 0,
    cpu_percent: 0,
    uptime_formatted: '—',
    uptime_seconds: 0,
    version: '',
    last_update: null
  };

  var ANIMATED_KEYS = ['memory_used_mb', 'cpu_percent'];

  function assign(target, source) {
    Object.keys(source).forEach(function (key) { target[key] = source[key]; });
    return target;
  }

  function statsDashboard() {
    return {
      stats: assign({}, EMPTY_STATS),
      display: assign({}, EMPTY_STATS),
      fmt: global.Utils,
      loading: false,
      error: '',
      failures: 0,
      timer: null,
      
      randomWords: ['meow', 'miao', 'miau', 'nya', 'yaong', 'meo', 'mjau', 'miaou', 'niāo', 'myau', 'ngeong'],
      randomWord: 'meow',

      /* --- lifecycle --------------------------------------------------- */

      start: function () {
        var cached = global.Utils.storage.get(CACHE_KEY, null);
        if (cached) {
          // Filtered on read as well, so a cache written by an older build
          // cannot reintroduce fields the dashboard no longer shows.
          var self0 = this;
          Object.keys(EMPTY_STATS).forEach(function (key) {
            if (key in cached) {
              self0.stats[key] = cached[key];
              self0.display[key] = cached[key];
            }
          });
        }
        this.refresh();

        var self = this;
        
        // Randomize word periodically
        setInterval(function() {
            self.randomWord = self.randomWords[Math.floor(Math.random() * self.randomWords.length)];
        }, 5000);
        
        // Pause polling while the tab is hidden — nothing to render, and it
        // keeps the free-tier instance from doing pointless work.
        document.addEventListener('visibilitychange', function () {
          if (document.hidden) {
            self.clearTimer();
          } else {
            self.refresh();
          }
        });
      },

      clearTimer: function () {
        if (this.timer) {
          clearTimeout(this.timer);
          this.timer = null;
        }
      },

      schedule: function () {
        this.clearTimer();
        if (document.hidden) return;

        var delay = this.failures > 0
          ? Math.min(BASE_INTERVAL * Math.pow(2, this.failures), MAX_INTERVAL)
          : BASE_INTERVAL;
        // Jitter keeps many open tabs from hitting the API in lockstep.
        delay += global.Utils.randomBetween(0, 750);

        var self = this;
        this.timer = setTimeout(function () { self.refresh(); }, delay);
      },

      refresh: function () {
        if (this.loading) return;
        this.loading = true;
        var self = this;

        var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
        var timeout = setTimeout(function () {
          if (controller) controller.abort();
        }, REQUEST_TIMEOUT);

        fetch('/api/stats', {
          headers: { 'Accept': 'application/json' },
          cache: 'no-store',
          signal: controller ? controller.signal : undefined
        })
          .then(function (response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.json();
          })
          .then(function (data) {
            self.apply(data);
            self.failures = 0;
            self.error = '';
            // Cache the displayed subset only — no code data lands in
            // localStorage just because the API happened to return it.
            global.Utils.storage.set(CACHE_KEY, assign({}, self.stats));
          })
          .catch(function (err) {
            self.failures += 1;
            self.error = 'Connection lost (' + (err.message || 'error') + ') — showing last known values';
          })
          .finally(function () {
            clearTimeout(timeout);
            self.loading = false;
            self.schedule();
          });
      },

      apply: function (data) {
        var self = this;
        // Copy only the displayed keys; the rest of the payload is ignored.
        Object.keys(EMPTY_STATS).forEach(function (key) {
          if (!(key in data)) return;
          self.stats[key] = data[key];
          if (ANIMATED_KEYS.indexOf(key) === -1) self.display[key] = data[key];
        });
        this.animateNumbers(data);
      },

      /* Smoothly count each numeric card up to its new value. */
      animateNumbers: function (data) {
        var self = this;
        ANIMATED_KEYS.forEach(function (key) {
          var from = global.Utils.toNumber(self.display[key]);
          var to = global.Utils.toNumber(data[key]);
          if (from === to) return;
          if (Math.abs(to - from) < 0.05) {
            self.display[key] = to;
            return;
          }

          var duration = 550;
          var startedAt = null;
          function step(now) {
            if (startedAt === null) startedAt = now;
            var progress = global.Utils.clamp((now - startedAt) / duration, 0, 1);
            var eased = 1 - Math.pow(1 - progress, 3);
            self.display[key] = from + (to - from) * eased;
            if (progress < 1) requestAnimationFrame(step);
            else self.display[key] = to;
          }
          requestAnimationFrame(step);
        });
      },

      /* --- derived state ------------------------------------------------ */

      get memoryClass() {
        var percent = global.Utils.toNumber(this.stats.memory_percent);
        if (percent >= 90) return 'card-bad';
        if (percent >= 70) return 'card-warn';
        return '';
      },

      get cpuClass() {
        return global.Utils.toNumber(this.stats.cpu_percent) >= 80 ? 'card-warn' : '';
      }
    };
  }

  global.statsDashboard = statsDashboard;

  document.addEventListener('alpine:init', function () {
    global.Alpine.data('statsDashboard', statsDashboard);
  });
})(window);
