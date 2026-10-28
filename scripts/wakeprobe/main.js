// WakeProbe: reports what webapis.epaper can do, sets a wake-up and sleeps.
// The plan comes from the Mac server and is fetched again after every wake-up:
// {"wake_in_s": 180, "sleep_after_s": 30, "network_standby": "OFF", "refresh": false}
// An empty plan ({}) leaves the panel alone.
var SERVER = "http://192.100.3.87:3000";
var BUILD = "__BUILD__";
var lines = [];
var lastTick = Date.now();
var cycle = 0;

function show(text) {
  lines.push(new Date().toTimeString().slice(0, 8) + " " + text);
  if (lines.length > 14) lines.shift();
  var el = document.getElementById("log");
  if (el) el.textContent = lines.join("\n");
}

function post(kind, data, done) {
  var body = JSON.stringify({ kind: kind, build: BUILD, now: new Date().toString(), data: data });
  try {
    var x = new XMLHttpRequest();
    x.open("POST", SERVER + "/report", true);
    x.setRequestHeader("Content-Type", "text/plain");
    x.onloadend = function () { if (done) done(x.status); };
    x.send(body);
  } catch (e) {
    new Image().src = SERVER + "/beacon?k=" + encodeURIComponent(kind) + "&e=" + encodeURIComponent(String(e));
    if (done) done(0);
  }
}

function err(e) {
  if (!e) return null;
  return { name: e.name, code: e.code, message: e.message, text: String(e) };
}

function call(name, fn) {
  try {
    var v = fn();
    return { ok: true, value: v === undefined ? "(undefined)" : v };
  } catch (e) {
    return { ok: false, error: err(e) };
  }
}

function members(obj) {
  var names = [];
  for (var k in obj) names.push(k);
  return names;
}

window.onerror = function (msg, src, line, col, e) {
  post("onerror", { msg: String(msg), src: src, line: line, col: col, error: err(e) });
};

// Every lifecycle event we can think of, to learn which one fires after a wake-up.
["visibilitychange", "pageshow", "pagehide", "focus", "blur", "online", "offline", "resume", "pause", "freeze"].forEach(function (name) {
  var target = (name === "visibilitychange" || name === "resume" || name === "pause" || name === "freeze") ? document : window;
  target.addEventListener(name, function () {
    post("event", { name: name, visibility: document.visibilityState, online: navigator.onLine, since_tick_s: Math.round((Date.now() - lastTick) / 1000) });
  });
});

function probe() {
  var r = {
    href: location.href,
    tz_offset_min: new Date().getTimezoneOffset(),
    has_webapis: typeof webapis !== "undefined",
    has_tizen: typeof tizen !== "undefined",
    online: navigator.onLine
  };
  if (r.has_webapis && webapis.epaper) {
    var ep = webapis.epaper;
    r.getVersion = call("getVersion", function () { return ep.getVersion(); });
    r.isScheduledPlayBootReason = call("isScheduledPlayBootReason", function () { return ep.isScheduledPlayBootReason(); });
    r.getAutoSleepTime = call("getAutoSleepTime", function () { return ep.getAutoSleepTime(); });
    r.getNetworkStandby = call("getNetworkStandby", function () { return ep.getNetworkStandby(); });
  }
  if (r.has_webapis && webapis.systemcontrol) {
    var sc = webapis.systemcontrol;
    r.systemcontrol_members = members(sc);
    r.getSerialNumber = call("getSerialNumber", function () { return sc.getSerialNumber(); });
    r.getCustomAppInfo = call("getCustomAppInfo", function () { return sc.getCustomAppInfo(); });
    r.getButtonLock = call("getButtonLock", function () { return sc.getButtonLock(); });
    r.getOnScreenMenuOrientation = call("getOnScreenMenuOrientation", function () { return sc.getOnScreenMenuOrientation(); });
    r.isCustomAppDownloaded = call("isCustomAppDownloaded", function () { return sc.isCustomAppDownloaded(); });
  }
  if (r.has_webapis && webapis.timer) {
    var tm = webapis.timer;
    r.timer_members = members(tm);
    r.getCurrentTime = call("getCurrentTime", function () { return tm.getCurrentTime(); });
    r.getNTP = call("getNTP", function () { return tm.getNTP(); });
    r.getDST = call("getDST", function () { return tm.getDST(); });
  }
  if (r.has_webapis && webapis.remotepower) r.remotepower_members = members(webapis.remotepower);
  if (r.has_webapis && webapis.systeminfo) r.webapis_systeminfo_members = members(webapis.systeminfo);
  return r;
}

// tizen.systeminfo may never call back (seen after a wake-up), so give up after 3 s.
function battery(done) {
  var finished = false;
  function finish(r) { if (!finished) { finished = true; done(r); } }
  setTimeout(function () { finish({ ok: false, error: "timeout" }); }, 3000);
  if (typeof tizen === "undefined" || !tizen.systeminfo) { finish({ ok: false, error: "no tizen.systeminfo" }); return; }
  try {
    tizen.systeminfo.getPropertyValue("BATTERY", function (b) {
      finish({ ok: true, level: b.level, isCharging: b.isCharging });
    }, function (e) { finish({ ok: false, error: err(e) }); });
  } catch (e) {
    finish({ ok: false, error: err(e) });
  }
}

function wakeupTime(d) {
  return {
    year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
    hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds()
  };
}

function run(plan) {
  var ep = webapis.epaper;
  cycle += 1;
  var r = { plan: plan, cycle: cycle };
  if (plan.restore_standby) r.restoreNetworkStandby = call("setNetworkStandby", function () { return ep.setNetworkStandby(plan.restore_standby); });
  if (plan.auto_sleep) r.setAutoSleepTime = call("setAutoSleepTime", function () { return ep.setAutoSleepTime(plan.auto_sleep); });
  if (plan.wake_in_s) {
    var at = new Date(Date.now() + plan.wake_in_s * 1000);
    r.wake_at = wakeupTime(at);
    r.setScheduleWakeupTime = call("setScheduleWakeupTime", function () { return ep.setScheduleWakeupTime(r.wake_at); });
  }
  if (plan.refresh) r.screenRefreshNow = call("screenRefreshNow", function () { return ep.screenRefreshNow(); });
  show("cycle " + cycle + " wake " + JSON.stringify(r.wake_at || null));
  post("plan", r, function () {
    if (!plan.sleep_after_s) return;
    setTimeout(function () {
      var s = {};
      if (plan.network_standby) {
        s.setNetworkStandby = call("setNetworkStandby", function () { return ep.setNetworkStandby(plan.network_standby); });
        s.getNetworkStandby = call("getNetworkStandby", function () { return ep.getNetworkStandby(); });
      }
      show("sleep");
      post("sleep", s, function () {
        lastTick = Date.now();
        var g = call("goToSleep", function () { return ep.goToSleep(); });
        post("sleep-result", g);
      });
    }, plan.sleep_after_s * 1000);
  });
}

function fetchPlan(why) {
  var x = new XMLHttpRequest();
  x.open("GET", SERVER + "/plan?why=" + why + "&t=" + Date.now(), true);
  x.onload = function () {
    var plan = {};
    try { plan = JSON.parse(x.responseText); } catch (e) { post("plan-parse", err(e)); }
    run(plan);
  };
  x.onerror = function () {
    show("plan fetch failed (" + why + ")");
    post("plan-fetch-failed", { why: why, online: navigator.onLine });
  };
  x.send();
}

// The panel resumes the app after a wake-up instead of reloading it: a gap in
// the heartbeat means we were asleep.
function heartbeat() {
  var now = Date.now();
  var gap = Math.round((now - lastTick) / 1000);
  lastTick = now;
  if (gap > 45) {
    var info = {
      gap_s: gap,
      online: navigator.onLine,
      isScheduledPlayBootReason: call("isScheduledPlayBootReason", function () { return webapis.epaper.isScheduledPlayBootReason(); }),
      getNetworkStandby: call("getNetworkStandby", function () { return webapis.epaper.getNetworkStandby(); }),
      visibility: document.visibilityState
    };
    show("resumed after " + gap + " s");
    post("resume-early", { gap_s: gap, online: navigator.onLine });
    battery(function (b) {
      info.battery = b;
      post("resume", info, function () { fetchPlan("resume"); });
    });
  }
}

function start() {
  document.getElementById("stamp").textContent = BUILD + " " + new Date().toLocaleString();
  var info = probe();
  show("boot reason " + JSON.stringify(info.isScheduledPlayBootReason || null));
  battery(function (b) {
    info.battery = b;
    post("boot", info, function () { fetchPlan("boot"); });
  });
}

window.onload = function () {
  start();
  setInterval(heartbeat, 15000);
};
