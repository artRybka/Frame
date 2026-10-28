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
  // After a change of the screen the panel prepares ~10 s and redraws ~30 s.
  // goToSleep() does not wait for it: a sleep mid-refresh left a half-drawn
  // grey screen and lost the alarm (E16). Sleep this long after the last one.
  var SETTLE_MS = 60000;
  // An alarm this close by the time the app may sleep: ask again instead.
  var MIN_AHEAD_MS = 2 * 60000;
  var ATTEMPTS = 4;
  var ATTEMPT_DELAY_MS = 5000;
  // "wait" answers in a row before giving up on the server for now.
  var MAX_WAITS = 30;
  var RELOAD_EVERY_MS = 10 * 60000;
  // The panel's Wi-Fi is weak (60-215 KB/s, E16): a picture may take minutes.
  var DOWNLOAD_TIMEOUT_MS = 5 * 60000;
  var PROGRESS_EVERY_MS = 2000;
  // The Wi-Fi is read at every start and wake, and on the charger this often.
  var WIFI_EVERY_MS = 5 * 60000;
  var WIFI_TIMEOUT_MS = 10000;

  var ep = (typeof webapis !== "undefined" && webapis.epaper) ? webapis.epaper : null;
  var shown = null;
  var busy = false;
  var waits = 0;
  var timer = null;
  var last = Date.now();
  var drawnAt = 0;  // the last change of the screen
  var wifiAt = 0;

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
    if (!el || el.textContent === (text || "")) return;
    el.textContent = text || "";
    drawnAt = Date.now();
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

  // Up again after a sleep with the Wi-Fi off: back on in standby, so that
  // Wake-on-LAN reaches the panel should it fall asleep on its own (E16).
  function wifiBack() {
    if (!ep) return;
    var now = call(function () { return ep.getNetworkStandby(); });
    if (now.ok && now.value === "OFF") {
      var r = call(function () { return ep.setNetworkStandby("ON"); });
      report("standby", { restored: r });
    }
  }

  // The panel's Wi-Fi for the iOS app (signal, network, address): from
  // webapis.network, which needs the privilege network.public (package
  // 1.2.0+), else from tizen.systeminfo (signal 0-1, no frequency).
  function wifi() {
    wifiAt = Date.now();
    var data = {};
    var n = (typeof webapis !== "undefined" && webapis.network) ? webapis.network : null;
    if (n) {
      var level = call(function () { return n.getWiFiSignalStrengthLevel(); });
      if (level.ok && level.value !== null) {
        data.via = "webapis";
        data.level = Number(level.value);
        data.ssid = call(function () { return n.getWiFiSsid(); }).value;
        data.ip = call(function () { return n.getIp(); }).value;
        data.frequency = call(function () { return n.getWiFiFrequency(); }).value;
        report("wifi", data);
        return;
      }
      data.webapis_error = level.error;
    }
    var sent = false;
    var send = function (more) {
      if (sent) return;
      sent = true;
      for (var k in more) data[k] = more[k];
      report("wifi", data);
    };
    var info = (typeof tizen !== "undefined" && tizen.systeminfo) ? tizen.systeminfo : null;
    if (!info) return send({});
    var r = call(function () {
      info.getPropertyValue("WIFI_NETWORK", function (w) {
        send({ via: "systeminfo", signal: w.signalStrength, ssid: w.ssid, ip: w.ipAddress, status: w.status });
      }, function (e) {
        send({ error: String(e && e.message ? e.message : e) });
      });
    });
    if (!r.ok) return send({ error: r.error });
    // After a wake systeminfo may never call back (E16).
    setTimeout(function () { send({ error: "no answer" }); }, WIFI_TIMEOUT_MS);
  }

  function ask(reason) {
    if (busy) return;
    busy = true;
    clearTimeout(timer);
    if (reason !== "poll" && reason !== "retry") wifiBack();
    if ((reason !== "poll" && reason !== "retry") || Date.now() - wifiAt > WIFI_EVERY_MS) wifi();
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
    draw(answer, function () {
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
      }, 2000);
    });
  }

  // The whole picture is downloaded before it goes on the page: an <img>
  // loading while the e-paper refreshes was 4-10x slower (E16). The server
  // hears how far it is, for the progress bar in the iOS app.
  function download(src, fileId, ok, fail) {
    var x = new XMLHttpRequest();
    var told = 0;
    x.open("GET", src, true);
    x.responseType = "blob";
    x.timeout = DOWNLOAD_TIMEOUT_MS;
    x.onprogress = function (e) {
      var now = Date.now();
      if (!e.lengthComputable || now - told < PROGRESS_EVERY_MS) return;
      told = now;
      report("progress", { file_id: fileId, loaded: e.loaded, total: e.total });
    };
    x.onload = function () {
      if (x.status !== 200) return fail("HTTP " + x.status);
      ok(x.response);
    };
    x.onerror = function () { fail("network"); };
    x.ontimeout = function () { fail("timeout"); };
    x.send();
  }

  function draw(answer, done) {
    if (!answer.image || answer.file_id === shown) return done(false);
    var started = Date.now();
    download(answer.image, answer.file_id, function (blob) {
      // blob: URLs do not load from the app's file:// origin (E16): the
      // picture goes on the page as a data URL, decoded first and set once.
      var reader = new FileReader();
      reader.onload = function () {
        var src = reader.result;
        var img = new Image();
        var put = function () {
          // With base_screen_resolution "always" the page is 2560x1440 and
          // the panel's picture is shown pixel for pixel (E16). A package
          // without it has a 1920x1080 page: the picture is scaled to fit.
          var w = window.innerWidth, h = window.innerHeight;
          var exact = img.naturalWidth === w && img.naturalHeight === h;
          var el = document.getElementById("picture");
          el.style.cssText = "position:fixed;left:0;top:0;width:" + w + "px;height:" + h + "px;display:block" +
            (exact ? ";image-rendering:pixelated" : "");
          el.src = src;
          nudge(el);
          note("");
          shown = answer.file_id;
          report("shown", {
            file_id: answer.file_id, width: img.naturalWidth, height: img.naturalHeight,
            bytes: blob.size, download_ms: Date.now() - started
          });
          done(true);
        };
        var failed = function () {
          report("error", { message: "image did not decode", image: answer.image });
          done(false);
        };
        img.src = src;
        if (img.decode) {
          img.decode().then(put, failed);
        } else {
          img.onload = put;
          img.onerror = failed;
        }
      };
      reader.onerror = function () {
        report("error", { message: "image could not be read", image: answer.image });
        done(false);
      };
      reader.readAsDataURL(blob);
    }, function (why) {
      report("error", { message: "image did not load: " + why, image: answer.image });
      done(false);
    });
  }

  // The e-paper does not redraw for a new picture alone (E16, the first one
  // stayed white): a small change of style makes it.
  function nudge(el) {
    el.style.opacity = "0.99";
    drawnAt = Date.now();
    setTimeout(function () {
      el.style.opacity = "1";
      drawnAt = Date.now();
    }, 300);
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

  // Show, let the refresh finish, set the alarm, sleep: in this order.
  function sleep(wakeMs, standby, why) {
    var settle = drawnAt + SETTLE_MS - Date.now();
    if (settle > 0) {
      clearTimeout(timer);
      timer = setTimeout(function () { sleep(wakeMs, standby, why); }, settle);
      return;
    }
    if (wakeMs && wakeMs - Date.now() < MIN_AHEAD_MS) {
      ask("late");  // a long download: the next change is (almost) here
      return;
    }
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
