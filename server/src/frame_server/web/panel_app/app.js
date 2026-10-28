// Frame app for the panel (Samsung "Custom" source, docs/WAKE.md E16).
//
// At every start and every wake: ask the server what to show (/panel/next),
// draw it, set the panel's own alarm for the next wake and go to sleep. The
// panel resumes the page after a wake instead of reloading it, so a gap in
// the heartbeat is how a wake is noticed. Alarms cannot be cancelled and the
// launcher sometimes restarts the app as it goes to sleep: nothing is
// planned here, every wake just asks again.
(function () {
  if (window.FrameApp) return;

  var SERVER = window.FRAME_SERVER;
  var BUILD = window.FRAME_BUILD || "";
  var CODE = window.FRAME_CODE || "local";
  var HEARTBEAT_MS = 15000;
  var ASLEEP_GAP_MS = 45000;
  // The e-paper redraws in about 30 s (E2): sleep only after that.
  var SETTLE_MS = 45000;
  var ATTEMPTS = 4;
  var ATTEMPT_DELAY_MS = 5000;
  // "wait" answers in a row before giving up on the server for now.
  var MAX_WAITS = 30;
  var RELOAD_EVERY_MS = 10 * 60000;

  var ep = (typeof webapis !== "undefined" && webapis.epaper) ? webapis.epaper : null;
  var shown = null;
  var busy = false;
  var waits = 0;
  var timer = null;
  var last = Date.now();

  function saved(key, value) {
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem("frame." + key));
      localStorage.setItem("frame." + key, JSON.stringify(value));
    } catch (e) {
      return null;
    }
    return value;
  }

  function call(fn) {
    try {
      var value = fn();
      return { ok: true, value: value === undefined ? null : value };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }

  function note(text) {
    var el = document.getElementById("note");
    if (el) el.textContent = text || "";
  }

  function report(event, data, done) {
    var body = { event: event, build: BUILD, code: CODE, at: new Date().toString() };
    for (var k in data) body[k] = data[k];
    try {
      var x = new XMLHttpRequest();
      x.open("POST", SERVER + "/panel/report", true);
      x.setRequestHeader("Content-Type", "text/plain");
      x.timeout = 10000;
      x.onloadend = function () { if (done) done(); };
      x.send(JSON.stringify(body));
    } catch (e) {
      if (done) done();
    }
  }

  window.onerror = function (msg, src, line) {
    report("error", { message: String(msg), src: src, line: line });
  };

  function getJson(url, ok, fail) {
    var x = new XMLHttpRequest();
    x.open("GET", url, true);
    x.timeout = 15000;
    x.onload = function () {
      if (x.status !== 200) return fail("HTTP " + x.status);
      var data;
      try { data = JSON.parse(x.responseText); } catch (e) { return fail(String(e)); }
      ok(data);
    };
    x.onerror = function () { fail("network"); };
    x.ontimeout = function () { fail("timeout"); };
    x.send();
  }

  // The battery from webapis.deviced (tizen.systeminfo fails on the panel,
  // and after a wake may never call back); without it the server reads MDC.
  function battery() {
    var d = (typeof webapis !== "undefined" && webapis.deviced) ? webapis.deviced : null;
    if (!d) return "";
    var level = call(function () { return d.getBatteryCapacity(); });
    var source = call(function () { return d.getBatteryPowerSource(); });
    var q = "";
    if (level.ok && level.value !== null) q += "&battery=" + Number(level.value);
    if (source.ok && source.value) q += "&charging=" + (source.value !== "NO_CHARGER");
    return q;
  }

  function ask(reason) {
    if (busy) return;
    busy = true;
    clearTimeout(timer);
    var q = "reason=" + reason + "&build=" + encodeURIComponent(BUILD) +
      "&code=" + encodeURIComponent(CODE) +
      "&screen=" + window.innerWidth + "x" + window.innerHeight + "@" + (window.devicePixelRatio || 1) +
      battery();
    attempt(q, 1);
  }

  function attempt(q, n) {
    getJson(SERVER + "/panel/next?" + q, function (answer) {
      busy = false;
      saved("failures", 0);
      act(answer);
    }, function (why) {
      if (n < ATTEMPTS) {
        setTimeout(function () { attempt(q, n + 1); }, ATTEMPT_DELAY_MS);
        return;
      }
      busy = false;
      offline(why);
    });
  }

  // No server: sleep and try again later, a bit later each time.
  function offline(why) {
    var failures = (saved("failures") || 0) + 1;
    saved("failures", failures);
    var minutes = Math.min(15 * Math.pow(2, failures - 1), 360);
    if (!shown) note("Ramka nie łączy się z serwerem " + SERVER);
    sleep(Date.now() + minutes * 60000, null, "offline: " + why);
  }

  function act(answer) {
    if (answer.code && answer.code !== CODE) {
      var reloaded = saved("reloaded") || 0;
      if (Date.now() - reloaded > RELOAD_EVERY_MS) {
        saved("reloaded", Date.now());
        location.reload();  // the server's logic changed
        return;
      }
    }
    draw(answer, function (changed) {
      if (answer.action === "wait" || answer.action === "stay") {
        waits = answer.action === "wait" ? waits + 1 : 0;
        if (waits > MAX_WAITS) {
          waits = 0;
          offline("still waiting for a change");
          return;
        }
        timer = setTimeout(function () {
          ask(answer.action === "wait" ? "retry" : "poll");
        }, answer.wait_s * 1000);
        return;
      }
      waits = 0;
      timer = setTimeout(function () {
        sleep(answer.wake_ms, answer.standby, "plan");
      }, changed ? SETTLE_MS : 2000);
    });
  }

  function draw(answer, done) {
    if (!answer.image || answer.file_id === shown) return done(false);
    var img = new Image();
    img.onload = function () {
      var el = document.getElementById("picture");
      el.src = img.src;
      el.style.display = "block";
      note("");
      shown = answer.file_id;
      report("shown", { file_id: answer.file_id, width: img.naturalWidth, height: img.naturalHeight });
      done(true);
    };
    img.onerror = function () {
      report("error", { message: "image did not load", image: answer.image });
      done(false);
    };
    img.src = answer.image;
  }

  // The panel's alarm, in its local time. Alarms add up and cannot be
  // cancelled: one already set for that moment is not set again.
  function arm(ms) {
    var now = Date.now();
    var armed = (saved("alarms") || []).filter(function (t) { return t > now; });
    if (armed.indexOf(ms) >= 0) return { ok: true, value: "already set" };
    var d = new Date(ms);
    var result = call(function () {
      return ep.setScheduleWakeupTime({
        year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
        hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds()
      });
    });
    if (result.ok) {
      armed.push(ms);
      saved("alarms", armed);
    }
    return result;
  }

  function sleep(wakeMs, standby, why) {
    var r = { why: why, wake: wakeMs ? new Date(wakeMs).toString() : null };
    if (ep) {
      if (standby) {
        var now = call(function () { return ep.getNetworkStandby(); });
        if (!now.ok || now.value !== standby) {
          r.standby = call(function () { return ep.setNetworkStandby(standby); });
        }
      }
      if (wakeMs) r.alarm = arm(wakeMs);
    }
    report("sleep", r, function () {
      last = Date.now();
      if (!ep) return;
      var s = call(function () { return ep.goToSleep(); });
      if (!s.ok) report("error", { message: "goToSleep failed", detail: s.error });
    });
  }

  function heartbeat() {
    var now = Date.now();
    var gap = now - last;
    last = now;
    if (gap > ASLEEP_GAP_MS) {
      var alarm = ep ? call(function () { return ep.isScheduledPlayBootReason(); }) : null;
      ask(alarm && alarm.ok && Number(alarm.value) === 1 ? "wake" : "resume");
    }
  }

  window.FrameApp = { ask: ask, version: CODE };
  setInterval(heartbeat, HEARTBEAT_MS);
  ask("start");
})();
