// Frame app for the panel (Samsung "Custom" source, docs/WAKE.md E16).
//
// At every start and every wake: ask the server what to show (/panel/next),
// draw it, set the panel's own alarm for the next wake and go to sleep. The
// panel resumes the page after a wake instead of reloading it, so a gap in
// the heartbeat is how a wake is noticed. Alarms cannot be cancelled and the
// launcher sometimes restarts the app as it goes to sleep: nothing is
// planned here, every wake just asks again.
//
// A sleep with the Wi-Fi off ends in a cold boot, and the server starts the
// app only when there is something new (panel_app.py): so before it the app
// sets the alarms for all the checks up to the next change, and a picture
// already on the screen is never drawn again.
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
  // Started by the launcher (a cold start, or a start over MDC), the panel
  // first redraws Samsung's install screen and only then the page: the
  // picture shown 10 s after the start began to refresh 70 s later, and a
  // sleep 60 s after it cut the refresh short (2026-10-30, a purple, half
  // drawn picture). Sleep no sooner than this after the page loaded.
  var START_SETTLE_MS = 150000;
  // An alarm this close by the time the app may sleep: ask again instead.
  // JS runs up to ~130 s after goToSleep() and an alarm due before the
  // panel is really down is lost (E16), so keep a margin of 4 minutes.
  var MIN_AHEAD_MS = 4 * 60000;
  // Woken by an alarm with nothing new, the panel is left alone and goes
  // back to sleep after this much idleness (20 minutes as set by hand).
  // 5 minutes until 2026-11-05: an empty check cost ~1% of the battery
  // (Mateusz: "sprawdzenie bez zmiany obrazu teraz sporo kosztuje"). Not
  // shorter: at a wake that needs it the app starts up to ~90 s after the
  // panel (Tizen's alarm, 22:20 that evening), and has to beat this. A
  // panel refusing it keeps the old value. The setter takes only OFF, 3MIN,
  // 5MIN, 10MIN, 20MIN, 30MIN, 60MIN: "2MIN" threw TypeMismatchError
  // (2026-11-05 23:02).
  var AUTO_SLEEP = "3MIN";
  var AUTO_SLEEP_FALLBACK = "5MIN";
  var ATTEMPTS = 4;
  var ATTEMPT_DELAY_MS = 5000;
  // On the charger without the server: ask again after 1, 2, ... minutes, at
  // most this many.
  var OFFLINE_RETRIES = 5;
  // "wait" answers in a row before giving up on the server for now.
  var MAX_WAITS = 30;
  var RELOAD_EVERY_MS = 10 * 60000;
  // The panel's Wi-Fi is weak (60-215 KB/s, E16): a picture may take minutes.
  var DOWNLOAD_TIMEOUT_MS = 5 * 60000;
  var PROGRESS_EVERY_MS = 2000;
  // The Wi-Fi is read at every start and wake, and on the charger this often.
  var WIFI_EVERY_MS = 5 * 60000;
  var WIFI_TIMEOUT_MS = 10000;

  // A question with no answer this long (a request that never ended): ask
  // again instead of waiting for it forever.
  var STUCK_MS = 2 * 60000;
  // Still running this long after goToSleep() (JS runs on up to ~130 s while
  // the panel goes down, E16): the panel stayed up, or magic packets woke it
  // again seconds after it went down, a gap too short to notice (2026-11-01,
  // a picture sent right after a status check: silent until the button).
  // Ask again instead of waiting for a wake that already happened.
  var STILL_UP_MS = 4 * 60000;
  // A screenshot a minute after a drawing at the earliest (capture()): 33 s
  // after one it was still all white (2026-11-04).
  var CAPTURE_SETTLE_MS = 60000;
  // ...and 100 s after the page loaded: started by the launcher, the panel
  // shows Samsung's "Custom App" screen for ~70 s, and a screenshot then
  // is that screen (2026-11-05 16:00, a check bringing a new picture).
  var CAPTURE_START_MS = 100000;
  var capturing = false;  // a screenshot waits for CAPTURE_SETTLE_MS

  var ep = (typeof webapis !== "undefined" && webapis.epaper) ? webapis.epaper : null;
  var busy = false;
  var rebooting = 0;  // rebootDevice() called (ms): the panel goes down
  var REBOOT_WAIT_MS = 5 * 60000;  // still up after this: ask again
  var busySince = 0;
  var gap = 0;  // the last heartbeat gap: how long the panel was down
  var waits = 0;
  var timer = null;
  var last = Date.now();
  var drawnAt = 0;  // the last change of the screen
  var loadedAt = Date.now();
  var wifiAt = 0;
  var sleptAt = 0;  // goToSleep() called and no question since

  function saved(key, value) {
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem("frame." + key));
      localStorage.setItem("frame." + key, JSON.stringify(value));
    } catch (e) {
      return null;
    }
    return value;
  }

  // The picture on the screen, kept across starts: after a full sleep the
  // app starts from scratch, and drawing the same picture again blinks the
  // e-paper for ~40 s for nothing. Only for this package: a new one comes
  // with the launcher's install screen.
  var screen = saved("screen");
  var shown = screen && screen.build === BUILD ? screen.file_id : null;

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
    x.timeout = 15000;
    x.onload = function () {
      if (x.status !== 200) return fail("HTTP " + x.status);
      var data;
      try { data = JSON.parse(x.responseText); } catch (e) { return fail(String(e)); }
      ok(data);
    };
    x.onerror = function () { fail("network"); };
    x.ontimeout = function () { fail("timeout"); };
    try {
      x.open("GET", url, true);
      x.send();
    } catch (e) {
      setTimeout(function () { fail(String(e)); }, 0);
    }
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

  function onCharger() {
    var d = (typeof webapis !== "undefined" && webapis.deviced) ? webapis.deviced : null;
    var source = d ? call(function () { return d.getBatteryPowerSource(); }) : null;
    return !!(source && source.ok && source.value && source.value !== "NO_CHARGER");
  }

  // Up again after a sleep with the Wi-Fi off: back on in standby, so that
  // Wake-on-LAN reaches the panel should it fall asleep on its own (E16),
  // and the auto sleep back to what it was.
  function wifiBack() {
    if (!ep) return;
    var now = call(function () { return ep.getNetworkStandby(); });
    if (now.ok && now.value === "OFF") {
      var r = call(function () { return ep.setNetworkStandby("ON"); });
      report("standby", { restored: r });
    }
    var before = saved("autoSleep");
    if (before) {
      var a = call(function () { return ep.setAutoSleepTime(before); });
      if (a.ok) saved("autoSleep", null);
      report("auto-sleep", { restored: before, result: a });
    }
  }

  // getAutoSleepTime() says minutes (20), the setter wants "20MIN" or "OFF".
  function shortAutoSleep() {
    var now = call(function () { return ep.getAutoSleepTime(); });
    if (!now.ok || now.value === null) return now;
    var minutes = Number(now.value);
    if (!saved("autoSleep")) saved("autoSleep", minutes > 0 ? minutes + "MIN" : "OFF");
    var set = call(function () { return ep.setAutoSleepTime(AUTO_SLEEP); });
    var read = call(function () { return ep.getAutoSleepTime(); });
    if (set.ok && read.ok && Number(read.value) === parseInt(AUTO_SLEEP, 10)) return { ok: true, value: AUTO_SLEEP };
    var back = call(function () { return ep.setAutoSleepTime(AUTO_SLEEP_FALLBACK); });
    return { ok: back.ok, value: AUTO_SLEEP_FALLBACK, refused: AUTO_SLEEP, tried: set, read: read, error: back.error };
  }

  // Samsung's daily screen refresh (03:00 out of the box) wakes the panel
  // on its own, also from a sleep with the Wi-Fi off (2026-10-31: up for
  // 5 minutes at 03:00 before a 07:00 alarm). Moved to the time of the
  // next wake, it rides along with a wake that happens anyway.
  function refreshAt(ms) {
    var d = new Date(ms);
    var now = call(function () { return ep.getScreenRefreshTime(); });
    if (now.ok && now.value && Number(now.value.hour) === d.getHours() &&
        Number(now.value.minute) === d.getMinutes()) return null;
    return call(function () {
      return ep.setScreenRefreshTime({ hour: d.getHours(), minute: d.getMinutes() });
    });
  }

  // After a cold boot (an alarm from a sleep with the Wi-Fi off, the
  // button) the launcher never starts the app, the server does over MDC
  // some 80 s later (E19, 2026-11-05). Test (PLAN 2.6j): Tizen's own alarm
  // manager starts the app it names when it does not run, so each panel
  // alarm of such a sleep gets one, half a minute later (the panel alarm
  // rings 20-40 s early, the launcher is up ~45-60 s after it), by the
  // panel's clock like the panel alarms (privilege alarm, package with it
  // on). Tizen's alarms, unlike the panel's, can be removed: the old ones
  // go first.
  var LAUNCH_AFTER_MS = 30000;

  function launchAlarms(times) {
    var t = typeof tizen !== "undefined" ? tizen : null;
    if (!t || !t.alarm || !t.application) return { ok: false, error: "no tizen.alarm" };
    var app = call(function () { return t.application.getCurrentApplication().appInfo.id; });
    if (!app.ok) return app;
    var cleared = call(function () { return t.alarm.removeAll(); });
    var shift = panelShift();
    var set = times.map(function (ms) {
      var at = new Date(ms + LAUNCH_AFTER_MS + shift);
      var r = call(function () { return t.alarm.add(new t.AlarmAbsolute(at), app.value); });
      return r.ok ? at.toTimeString().slice(0, 8) : r.error;
    });
    return { ok: true, app: app.value, cleared: cleared.ok ? true : cleared.error, set: set, shift_s: Math.round(shift / 1000) };
  }

  // How this start came about, for the test of Tizen's alarms: the app
  // control it was started with and the alarms Tizen still holds.
  function launchReport() {
    var t = typeof tizen !== "undefined" ? tizen : null;
    if (!t || !t.application) return;
    var r = {};
    r.control = call(function () {
      var c = t.application.getCurrentApplication().getRequestedAppControl();
      return c && c.appControl ? { operation: c.appControl.operation, caller: c.callerAppId } : null;
    });
    r.alarms = t.alarm ? call(function () {
      return t.alarm.getAll().map(function (a) {
        return a.getNextScheduledDate ? String(a.getNextScheduledDate()) : String(a.id);
      });
    }) : { ok: false, error: "no tizen.alarm" };
    r.boot = ep ? call(function () { return ep.isScheduledPlayBootReason(); }) : null;
    r.page_ms = Math.round(performance.now());
    report("launch", r);
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
        data.mac = call(function () { return n.getMac(); }).value;
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
    // Going down to install: no question, so no sleep either.
    var left = rebooting ? rebooting + REBOOT_WAIT_MS - Date.now() : 0;
    if (left > 0) {
      clearTimeout(timer);
      timer = setTimeout(function () { ask("retry"); }, left);
      return;
    }
    rebooting = 0;
    if (sleptAt) saved("alarms", null);  // down and up again since: gone
    sleptAt = 0;
    if (busy) return;
    busy = true;
    busySince = Date.now();
    clearTimeout(timer);
    if (reason !== "poll" && reason !== "retry") wifiBack();
    if ((reason !== "poll" && reason !== "retry") || Date.now() - wifiAt > WIFI_EVERY_MS) wifi();
    var q = "reason=" + reason + "&build=" + encodeURIComponent(BUILD) +
      "&code=" + encodeURIComponent(CODE) +
      "&screen=" + window.innerWidth + "x" + window.innerHeight + "@" + (window.devicePixelRatio || 1) +
      "&shown=" + encodeURIComponent(shown || "") +
      "&now=" + Date.now() +
      (reason === "resume" || reason === "wake" ? "&gap=" + Math.round(gap / 1000) : "") +
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

  // The charger is in (getBatteryPowerSource); null when unknown.
  // On the charger, else the last reading: a failed one (the panel going
  // down for a reboot, 2026-11-04 19:00) is no reason to sleep there.
  function plugged() {
    var d = (typeof webapis !== "undefined" && webapis.deviced) ? webapis.deviced : null;
    var source = d ? call(function () { return d.getBatteryPowerSource(); }) : null;
    if (source && source.ok && source.value) {
      var now = source.value !== "NO_CHARGER";
      saved("plugged", now);
      return now;
    }
    var last = saved("plugged");
    return typeof last === "boolean" ? last : null;
  }

  // No server: sleep and try again later, a bit later each time. On the
  // charger the app never sleeps: it stays up and asks again in a minute or
  // so. A server restarted for an update is away ~50 s, and a sleep then
  // left the frame down with no alarm that rang (2026-11-03, 22:56: silent
  // until the button, "Na baterii, bez Wi-Fi" on the phone).
  function offline(why) {
    var failures = (saved("failures") || 0) + 1;
    saved("failures", failures);
    if (!shown) note("Ramka nie łączy się z serwerem " + SERVER);
    if (plugged()) {
      clearTimeout(timer);
      timer = setTimeout(function () { ask("retry"); }, Math.min(failures, OFFLINE_RETRIES) * 60000);
      return;
    }
    var minutes = Math.min(15 * Math.pow(2, failures - 1), 360);
    sleep(Date.now() + minutes * 60000, null, "offline: " + why);
  }

  function act(answer) {
    if (answer.code && answer.code !== CODE) {
      var reloaded = saved("reloaded") || 0;
      if (Date.now() - reloaded > RELOAD_EVERY_MS) {
        saved("reloaded", Date.now());
        // The new page starts white and the panel redraws it: the picture
        // has to go on it again (2026-11-04, white for 3 minutes after an
        // update of the server).
        saved("screen", null);
        location.reload();  // the server's logic changed
        return;
      }
    }
    if (answer.action === "reboot") return reboot();
    // On the charger: spare alarms, so that unplugged (it sleeps at once,
    // without the Wi-Fi) the frame wakes by itself (panel_app.py).
    if (answer.action === "stay" && ep && answer.wake_ms) spare([answer.wake_ms].concat(answer.wakes_ms || []));
    // The probe only on the charger: "stay" is also a frame kept awake
    // from the iOS app on battery.
    if (answer.action === "stay" && onCharger() && saved("probed") !== CODE) setTimeout(probe, 5000);
    // A screenshot when asked: on battery the server keeps the frame up for
    // it (an order from the iOS app). One at a time: the answers come every
    // 10 s. Timed once the answer's picture is drawn (capture after draw()).
    var shoot = answer.action === "stay" && answer.capture && !capturing;
    if (shoot) capturing = true;
    // Started over MDC by the server: the launcher's install screen drew
    // over the picture this page remembers (2026-11-04, white after an
    // update of the server).
    if (answer.redraw) {
      shown = null;
      saved("screen", null);
    }
    draw(answer, function () {
      if (shoot) {
        setTimeout(function () {
          capturing = false;
          capture();
        }, captureDelay());
      }
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
        sleep(answer.wake_ms, answer.standby, "plan", answer.wakes_ms);
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
          // The decoded image itself replaces the old one: one change of the
          // page, with the whole picture ready, and the panel refreshes once.
          // The opacity nudge (0.99, back to 1 after 300 ms) was for an
          // <img> still loading when the page changed (E16); as a second
          // change moments after the first it can be drawn as a second
          // refresh of the same picture once the first one is over.
          var old = document.getElementById("picture");
          img.id = "picture";
          img.alt = "";
          img.style.cssText = "position:fixed;left:0;top:0;width:" + w + "px;height:" + h + "px;display:block" +
            (exact ? ";image-rendering:pixelated" : "");
          old.parentNode.replaceChild(img, old);
          drawnAt = Date.now();
          note("");
          shown = answer.file_id;
          saved("screen", { file_id: shown, build: BUILD });
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

  // The panel's alarm, in its local time. Alarms add up and cannot be
  // cancelled: one already set for that moment is not set again. Only
  // within one awake period: a wake drops the panel's alarms (2026-11-02,
  // 07:00 kept from before two wakes was "already set", and neither it nor
  // 07:04 set just before a wake rang). Forgotten at every start and after
  // every sleep, so each sleep sets its own.
  saved("alarms", null);

  // How far the panel's own clock (webapis.timer, the one its alarms run
  // on) is from the page's. 2026-11-04 (E18): it said 2024-01-01 09:20
  // while the page knew the right time, an alarm at the right time failed
  // with UnknownError and one at the same distance on its clock was taken.
  // Within 2 minutes it counts as right: alarms go as they always did.
  var CLOCK_RIGHT_MS = 2 * 60000;

  function panelShift() {
    var t = (typeof webapis !== "undefined" && webapis.timer) ? webapis.timer : null;
    if (!t) return 0;
    var now = call(function () { return t.getCurrentTime(); });
    var v = now.ok ? now.value : null;
    if (!v || !v.year || !v.month) return 0;
    var at = new Date(v.year, v.month - 1, v.day || 1, v.hour || 0, v.minute || 0, v.second || 0);
    var shift = at.getTime() - Date.now();
    return isNaN(shift) || Math.abs(shift) < CLOCK_RIGHT_MS ? 0 : shift;
  }

  // The panel's own clock (webapis.timer) stood at 2024-01-01 while the
  // page's was right, and its alarms go by it (E18). It is set to the page's
  // time (privilege devicetimer, package 2.0.6 on), at most once an hour;
  // the shift in arm() stays for a package without it or a clock that
  // does not take the time.
  var CLOCK_SET_EVERY_MS = 60 * 60000;

  function setClock() {
    var t = (typeof webapis !== "undefined" && webapis.timer) ? webapis.timer : null;
    if (!t || !t.setCurrentTime) return;
    var before = panelShift();
    if (!before || Date.now() - (saved("clockSetAt") || 0) < CLOCK_SET_EVERY_MS) return;
    saved("clockSetAt", Date.now());
    var d = new Date();
    var r = call(function () {
      return t.setCurrentTime({
        year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
        hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds()
      });
    });
    var after = panelShift();
    r.before_s = Math.round(before / 1000);
    r.after_s = Math.round(after / 1000);
    // Alarms set by the old clock are years back by the new one: they do
    // not ring, and the ones still wanted are set again.
    if (!after) saved("alarms", []);
    report("clock", r);
  }

  function setAlarm(d) {
    return call(function () {
      return ep.setScheduleWakeupTime({
        year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
        hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds()
      });
    });
  }

  function arm(ms) {
    var now = Date.now();
    setClock();
    var armed = (saved("alarms") || []).filter(function (t) { return t > now; });
    if (armed.indexOf(ms) >= 0) return { ok: true, value: "already set" };
    var shift = panelShift();
    var result = setAlarm(new Date(ms + shift));
    if (shift) {
      result.shift_s = Math.round(shift / 1000);
      // Its clock read wrong: the right time, as before, is worth a try.
      if (!result.ok) {
        var plainTry = setAlarm(new Date(ms));
        plainTry.shift_s = 0;
        plainTry.shifted_error = result.error;
        result = plainTry;
      }
    }
    if (result.ok) {
      armed.push(ms);
      saved("alarms", armed);
    }
    return result;
  }

  function spare(times) {
    var set = [];
    times.forEach(function (ms) {
      var a = arm(ms);
      if (a.value !== "already set") {
        set.push(a.ok ? new Date(ms).toTimeString().slice(0, 5) + (a.shift_s ? " (zegar ramki " + a.shift_s + " s)" : "") : a.error);
      }
    });
    if (set.length) report("alarm", { spare: set });
  }

  // A newer package is on the server: the launcher installs it as the panel
  // boots (and does not start it; the server does over MDC, E16).
  // The panel takes a while to go down after rebootDevice() and the page
  // runs on: a question timing out then put it to sleep instead, with no
  // alarm, on the charger (2026-11-04 18:59, white until the button).
  function reboot() {
    var sc = (typeof webapis !== "undefined" && webapis.systemcontrol) ? webapis.systemcontrol : null;
    saved("screen", null);  // the boot and the install draw over it
    clearTimeout(timer);
    rebooting = Date.now();
    report("reboot", {}, function () {
      var r = sc ? call(function () { return sc.rebootDevice(); }) : { ok: false, error: "no systemcontrol" };
      if (!r.ok) {
        rebooting = 0;
        report("error", { message: "rebootDevice failed", detail: r.error });
        timer = setTimeout(function () { ask("retry"); }, 60000);
      }
    });
  }

  // Show, let the refresh finish, set the alarm, sleep: in this order.
  function sleep(wakeMs, standby, why, more) {
    var settle = Math.max(drawnAt + SETTLE_MS, loadedAt + START_SETTLE_MS) - Date.now();
    if (settle > 0) {
      clearTimeout(timer);
      timer = setTimeout(function () { sleep(wakeMs, standby, why, more); }, settle);
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
      if (wakeMs) {
        r.alarm = arm(wakeMs);
        r.refresh = refreshAt(wakeMs);
      }
      if (more && more.length) {
        r.more = more.map(function (ms) {
          var a = arm(ms);
          return a.ok ? new Date(ms).toTimeString().slice(0, 5) : a.error;
        });
        r.shift_s = r.alarm && r.alarm.shift_s;
      }
      // An alarm the server does not start the app for (a check with
      // nothing new, one set before a rest) boots the panel cold: it goes
      // back to sleep by itself, sooner than after its usual 20 minutes.
      if (standby === "OFF") r.autoSleep = shortAutoSleep();
      // Tizen's alarm starts the app only at the last one, which the server
      // would start it for anyway: at a check with nothing new the panel has
      // to go back to sleep untouched, a start there draws a white page over
      // the picture (2026-11-05, white all night).
      if (standby === "OFF" && wakeMs) r.launch = launchAlarms([more && more.length ? more[more.length - 1] : wakeMs]);
    }
    report("sleep", r, function () {
      last = Date.now();
      if (!ep) return;
      sleptAt = Date.now();
      var s = call(function () { return ep.goToSleep(); });
      if (!s.ok) report("error", { message: "goToSleep failed", detail: s.error });
    });
  }

  function heartbeat() {
    var now = Date.now();
    gap = now - last;
    last = now;
    if (busy && now - busySince > STUCK_MS) {
      report("error", { message: "a question never ended", since: new Date(busySince).toString() });
      busy = false;
    }
    if (gap > ASLEEP_GAP_MS) {
      var alarm = ep ? call(function () { return ep.isScheduledPlayBootReason(); }) : null;
      ask(alarm && alarm.ok && Number(alarm.value) === 1 ? "wake" : "resume");
    } else if (sleptAt && now - sleptAt > STILL_UP_MS) {
      ask("up");
    }
  }

  // How the launcher shows and hides the page (2026-10-30: a panel up
  // whose app never asked again): in the server's log.
  document.addEventListener("visibilitychange", function () {
    report("visibility", { state: document.visibilityState });
  });

  // A Tizen object as plain data: its values sit on getters of the
  // prototype, which JSON.stringify does not see.
  function plain(value, depth) {
    if (value === null || value === undefined) return null;
    var kind = typeof value;
    if (kind === "function") return undefined;
    if (kind !== "object") return value;
    if ((depth || 0) > 2) return String(value);
    if (Array.isArray(value)) {
      return value.map(function (v) { return plain(v, (depth || 0) + 1); });
    }
    var keys = [];
    for (var k in value) keys.push(k);
    try {
      for (var o = value; o && o !== Object.prototype; o = Object.getPrototypeOf(o)) {
        keys = keys.concat(Object.getOwnPropertyNames(o));
      }
    } catch (e) { /* the keys for-in found */ }
    var out = {};
    keys.forEach(function (key) {
      if (key === "constructor" || key in out) return;
      var v;
      try { v = value[key]; } catch (e) { v = String(e); }
      if (typeof v !== "function") out[key] = plain(v, (depth || 0) + 1);
    });
    return out;
  }

  // The names of what each webapis module offers: undocumented getters
  // (webapis.deviced is in no Samsung reference) show up here.
  function methods() {
    var out = {};
    if (typeof webapis === "undefined") return out;
    for (var name in webapis) {
      var module;
      try { module = webapis[name]; } catch (e) { continue; }
      if (!module || typeof module !== "object") continue;
      var list = [];
      for (var k in module) {
        try { if (typeof module[k] === "function") list.push(k); } catch (e) { /* skip */ }
      }
      out[name] = list.join(" ");
    }
    return out;
  }

  // Which clock the panel's alarms run on (2026-11-04): webapis.timer
  // says 2024-01-01 09:20 while the page's clock is right, and every spare
  // alarm on the charger fails with UnknownError. One alarm 2 h ahead on
  // each clock, read back and cancelled at once (cancelling works within
  // the same awake period, E16); on the charger, so a stray one is harmless.
  function alarmTest(w) {
    if (!ep) return;
    var out = {};
    var tv = w.timer ? call(function () { return w.timer.getCurrentTime(); }) : null;
    out.tv_now = tv;
    var tryAt = function (d) {
      var r = { at: d.toString() };
      r.set = call(function () {
        return ep.setScheduleWakeupTime({
          year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
          hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds()
        });
      });
      if (r.set.ok && r.set.value !== null) {
        r.read = call(function () { return plain(ep.getScheduleWakeupTime(r.set.value)); });
        r.cancel = call(function () { return ep.cancelScheduleWakeupTime(r.set.value); });
      }
      return r;
    };
    out.real_clock = tryAt(new Date(Date.now() + 2 * 3600000));
    if (tv && tv.ok && tv.value && tv.value.year) {
      var t = tv.value;
      var base = new Date(t.year, t.month - 1, t.day, t.hour, t.minute, t.second || 0);
      out.tv_clock = tryAt(new Date(base.getTime() + 2 * 3600000));
    }
    report("probe", { part: "alarm", alarm: out });
  }

  // Once per version of this code, on the charger only: what else the
  // panel can tell (docs/WAKE.md, "Sonda odczytów"). Read only, every call
  // on its own, async ones with a time limit; each part a report of its
  // own, so a part that fails does not take the others with it.
  function probe() {
    if (saved("probed") === CODE) return;
    saved("probed", CODE);
    var w = typeof webapis !== "undefined" ? webapis : {};
    var get = function (module, names) {
      var out = {};
      if (!module) return { missing: true };
      names.forEach(function (n) {
        out[n] = call(function () { return plain(module[n]()); });
      });
      return out;
    };
    var now = new Date();
    report("probe", { part: "time", date: now.toString(), utc_ms: now.getTime(),
      offset_min: now.getTimezoneOffset(),
      timer: get(w.timer, ["getCurrentTime", "getNTP", "getDST", "getSystemTimeSyncTimeout"]) });
    report("probe", { part: "epaper", epaper: get(w.epaper, ["getVersion", "getAutoSleepTime",
      "getScreenRefreshTime", "getBatteryWarningIconDisplay", "getNetworkStandby", "isScheduledPlayBootReason"]) });
    report("probe", { part: "system",
      systemcontrol: get(w.systemcontrol, ["getVersion", "getButtonLock", "getOnScreenMenuOrientation",
        "getCustomAppInfo", "isCustomAppDownloaded", "getMessageDisplay", "getAutoPowerOn"]),
      productinfo: get(w.productinfo, ["getFirmware", "getRealModel", "getModelCode", "getLocalSet",
        "isDisplayRotatorSupported"]) });
    report("probe", { part: "network", network: get(w.network, ["getVersion", "getActiveConnectionType",
      "isConnectedToGateway", "getIpMode", "getIp", "getSubnetMask", "getGateway", "getDns",
      "getSecondaryDns", "getMac", "getTVName", "getWiFiSsid", "getWiFiSignalStrengthLevel",
      "getWiFiFrequency", "getWiFiSecurityMode", "getWiFiEncryptionType"]) });
    // In pieces: the server's log keeps 4000 characters of a line.
    var all = methods(), piece = {}, size = 0, n = 0;
    Object.keys(all).forEach(function (name) {
      if (size + all[name].length > 2500 && size > 0) {
        report("probe", { part: "methods", n: ++n, methods: piece });
        piece = {};
        size = 0;
      }
      piece[name] = all[name];
      size += all[name].length + name.length;
    });
    if (size) report("probe", { part: "methods", n: ++n, methods: piece });
    report("probe", { part: "power", remotepower: get(w.remotepower, ["getVersion", "getPowerState",
      "getVirtualStandbyMode", "getVirtualStandbyRebootTime", "getRemoteConfiguration"]),
      timer: get(w.timer, ["getVersion"]) });
    alarmTest(w);
    var t = typeof tizen !== "undefined" ? tizen : null;
    if (!t) return;
    var info = t.systeminfo;
    var system = {
      memory_total: info ? call(function () { return info.getTotalMemory(); }) : null,
      memory_free: info ? call(function () { return info.getAvailableMemory(); }) : null,
      sensors: t.sensorservice ? call(function () { return t.sensorservice.getAvailableSensors(); }) : { missing: true }
    };
    var props = ["STORAGE", "MEMORY", "CPU", "DEVICE_ORIENTATION", "DISPLAY", "BUILD", "LOCALE"];
    var left = props.length;
    var sent = false;
    var send = function () {
      if (sent) return;
      sent = true;
      report("probe", { part: "systeminfo", systeminfo: system });
    };
    props.forEach(function (p) {
      var done = function (value) {
        if (system[p] !== undefined) return;
        system[p] = value;
        if (--left === 0) send();
      };
      var r = info ? call(function () {
        info.getPropertyValue(p, function (v) { done(plain(v)); },
          function (e) { done({ error: String(e && e.message ? e.message : e) }); });
      }) : { ok: false, error: "no systeminfo" };
      if (!r.ok) done({ error: r.error });
    });
    // After a wake systeminfo may never call back (E16).
    setTimeout(send, 15000);
    var a = t.application;
    if (!a) return;
    var vxt = "PbHvnmrROv.VXPlayer";
    var apps = {
      visibility: document.visibilityState,
      self: call(function () { var c = a.getCurrentApplication(); return { info: plain(c.appInfo), context: c.contextId }; }),
      vxt: call(function () { return plain(a.getAppInfo(vxt)); })
    };
    var told = false;
    var tell = function (running) {
      if (told) return;
      told = true;
      apps.running = running;
      report("probe", { part: "apps", apps: apps });
    };
    var r = call(function () {
      a.getAppsContext(function (list) {
        tell(list.map(function (c) { return c.appId; }));
      }, function (e) { tell({ error: String(e) }); });
    });
    if (!r.ok) tell(r);
    setTimeout(function () { tell({ error: "no answer" }); }, 5000);
  }

  // A screenshot of the panel, only when the owner asks for one (POST
  // /api/debug/panel-capture) and only on the charger: in E16 captureScreen
  // did not answer within 30 s, and it may hold the page up. The file goes
  // to the server as it is (text/plain: a simple request, no preflight).
  function captureDelay() {
    var now = Date.now();
    return Math.max(3000, drawnAt + CAPTURE_SETTLE_MS - now, loadedAt + CAPTURE_START_MS - now);
  }

  function capture() {
    var sc = (typeof webapis !== "undefined" && webapis.systemcontrol) ? webapis.systemcontrol : null;
    if (!sc) return report("capture", { error: "no systemcontrol" });
    var started = Date.now();
    var shot = call(function () { return sc.captureScreen("wgt-private-tmp"); });
    var took = Date.now() - started;
    report("capture", { result: shot, ms: took });
    if (!shot.ok) return;
    var fs = (typeof tizen !== "undefined") ? tizen.filesystem : null;
    var upload = function (blob, how) {
      var x = new XMLHttpRequest();
      x.open("POST", SERVER + "/panel/capture", true);
      x.setRequestHeader("Content-Type", "text/plain");
      x.timeout = 120000;
      x.onloadend = function () { report("capture", { uploaded: x.status, bytes: blob.size, via: how }); };
      x.send(blob);
    };
    // The page is a file:// origin: the file it names may read over XHR,
    // without the filesystem privilege (openFile and resolve: SecurityError,
    // 2026-11-04).
    if (typeof shot.value === "string" && shot.value.charAt(0) === "/") {
      var x = new XMLHttpRequest();
      x.open("GET", "file://" + shot.value, true);
      x.responseType = "blob";
      x.timeout = 20000;
      x.onloadend = function () {
        var blob = x.response;
        if (blob && blob.size > 0) return upload(blob, "file-xhr");
        report("capture", { error: "file:// read", status: x.status, size: blob ? blob.size : null });
      };
      try { x.send(); } catch (e) { report("capture", { error: "file:// send: " + String(e) }); }
    }
    if (!fs) return report("capture", { error: "no filesystem" });
    // The newer file API (Tizen 5+), else the older one.
    var r = call(function () {
      var h = fs.openFile("wgt-private-tmp/ScreenCapture.jpg", "r");
      var blob = h.readBlob();
      h.close();
      return blob;
    });
    if (r.ok && r.value) return upload(r.value, "openFile");
    var older = call(function () {
      fs.resolve("wgt-private-tmp/ScreenCapture.jpg", function (file) {
        file.openStream("r", function (stream) {
          var bin = atob(stream.readBase64(stream.bytesAvailable));
          stream.close();
          var bytes = new Uint8Array(bin.length);
          for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
          upload(new Blob([bytes], { type: "image/jpeg" }), "resolve");
        }, function (e) { report("capture", { error: "openStream: " + String(e) }); });
      }, function (e) { report("capture", { error: "resolve: " + String(e) }); }, "r");
    });
    report("capture", { openFile: r.ok ? "empty" : r.error, resolve: older.ok ? "asked" : older.error });
  }

  // The button on the frame and the battery as they change: for the log
  // first (2026-11-04), to see whether they reach the page at all.
  // The "next" button comes as ArrowRight (E18): the server shows the next
  // work, and the app asks for it at once instead of at its next poll.
  var keysTold = 0;
  function onKey(e) {
    var next = e.type === "keydown" && (e.key === "ArrowRight" || e.keyCode === 39);
    if (next) {
      report("key", { type: e.type, key: e.key, key_code: e.keyCode }, function () {
        setTimeout(function () { ask("poll"); }, 3000);
      });
      return;
    }
    if (keysTold >= 20) return;
    keysTold++;
    report("key", { type: e.type, key: e.key, key_code: e.keyCode, key_name: e.keyName });
  }
  document.addEventListener("keydown", onKey);
  window.addEventListener("tizenhwkey", onKey);

  var batteryTold = 0;
  function watchBattery() {
    var d = (typeof webapis !== "undefined" && webapis.deviced) ? webapis.deviced : null;
    if (!d) return;
    var tell = function (what) {
      return function () {
        if (batteryTold >= 60) return;
        batteryTold++;
        var args = [];
        for (var i = 0; i < arguments.length; i++) args.push(plain(arguments[i]));
        report("battery", {
          what: what, args: args,
          level: call(function () { return d.getBatteryCapacity(); }).value,
          source: call(function () { return d.getBatteryPowerSource(); }).value
        });
      };
    };
    var a = call(function () { return d.addBatteryCapacityListener(tell("capacity")); });
    var b = call(function () { return d.addChargingStatusListener(tell("charging")); });
    if (!a.ok || !b.ok) report("battery", { what: "listen", capacity: a, charging: b });
  }

  window.FrameApp = { ask: ask, version: CODE };
  setInterval(heartbeat, HEARTBEAT_MS);
  ask("start");
  watchBattery();
  launchReport();
})();
