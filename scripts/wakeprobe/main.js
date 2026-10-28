// WakeProbe: reports what webapis.epaper can do, sets a wake-up and sleeps.
// The plan (seconds until wake-up, delay before sleep) comes from the Mac server.
var SERVER = "http://192.100.3.87:3000";
var BUILD = "__BUILD__";
var lines = [];

function show(text) {
  lines.push(text);
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
    x.onloadend = function () { if (done) done(); };
    x.send(body);
  } catch (e) {
    new Image().src = SERVER + "/beacon?k=" + encodeURIComponent(kind) + "&e=" + encodeURIComponent(String(e));
    if (done) done();
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

window.onerror = function (msg, src, line, col, e) {
  post("onerror", { msg: String(msg), src: src, line: line, col: col, error: err(e) });
};

function probe() {
  var r = {
    href: location.href,
    ua: navigator.userAgent,
    tz_offset_min: new Date().getTimezoneOffset(),
    has_webapis: typeof webapis !== "undefined",
    has_tizen: typeof tizen !== "undefined"
  };
  if (r.has_webapis) {
    r.webapis_keys = Object.keys(webapis);
    r.has_epaper = !!webapis.epaper;
    if (webapis.epaper) {
      var ep = webapis.epaper;
      var names = [];
      for (var k in ep) names.push(k);
      r.epaper_members = names;
      r.getVersion = call("getVersion", function () { return ep.getVersion(); });
      r.isScheduledPlayBootReason = call("isScheduledPlayBootReason", function () { return ep.isScheduledPlayBootReason(); });
      r.getAutoSleepTime = call("getAutoSleepTime", function () { return ep.getAutoSleepTime(); });
      r.getNetworkStandby = call("getNetworkStandby", function () { return ep.getNetworkStandby(); });
      r.getBatteryWarningIconDisplay = call("getBatteryWarningIconDisplay", function () { return ep.getBatteryWarningIconDisplay(); });
      r.getScreenRefreshTime = call("getScreenRefreshTime", function () { return ep.getScreenRefreshTime(); });
    }
    if (webapis.productinfo) {
      r.duid = call("getDuid", function () { return webapis.productinfo.getDuid(); });
      r.firmware = call("getFirmware", function () { return webapis.productinfo.getFirmware(); });
    }
  }
  if (r.has_tizen) {
    r.tizen_app = call("app", function () { return tizen.application.getCurrentApplication().appInfo.id; });
  }
  return r;
}

function wakeupTime(d) {
  return {
    year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
    hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds()
  };
}

var lastTick = Date.now();
var cycle = 0;
var currentPlan = null;
var timerIds = [];

// The panel resumes the app after a wake-up instead of reloading it: a gap in
// the heartbeat means we were asleep, so report and start the next cycle.
function heartbeat() {
  var now = Date.now();
  var gap = Math.round((now - lastTick) / 1000);
  lastTick = now;
  if (gap > 45) {
    var ep = webapis.epaper;
    var info = {
      gap_s: gap,
      isScheduledPlayBootReason: call("isScheduledPlayBootReason", function () { return ep.isScheduledPlayBootReason(); }),
      visibility: document.visibilityState
    };
    show("resumed after " + gap + " s");
    post("resume", info, function () {
      if (currentPlan && cycle < (currentPlan.cycles || 1)) run(currentPlan);
    });
  }
}

document.addEventListener("visibilitychange", function () {
  post("visibility", { state: document.visibilityState, hidden: document.hidden });
});

function run(plan) {
  cycle += 1;
  currentPlan = plan;
  var ep = (typeof webapis !== "undefined") ? webapis.epaper : null;
  var r = { plan: plan, cycle: cycle };
  if (!ep) {
    post("plan", r);
    show("no webapis.epaper");
    return;
  }
  if (plan.network_standby) r.setNetworkStandby = call("setNetworkStandby", function () { return ep.setNetworkStandby(plan.network_standby); });
  if (plan.auto_sleep) r.setAutoSleepTime = call("setAutoSleepTime", function () { return ep.setAutoSleepTime(plan.auto_sleep); });
  if (plan.wake_in_s) {
    var at = new Date(Date.now() + plan.wake_in_s * 1000);
    r.wake_at = wakeupTime(at);
    if (timerIds.length) {
      var old = timerIds.pop();
      r.cancelScheduleWakeupTime = call("cancelScheduleWakeupTime", function () { return ep.cancelScheduleWakeupTime(old); });
    }
    r.setScheduleWakeupTime = call("setScheduleWakeupTime", function () { return ep.setScheduleWakeupTime(r.wake_at); });
    if (r.setScheduleWakeupTime.ok) {
      var id = r.setScheduleWakeupTime.value;
      timerIds.push(id);
      r.getScheduleWakeupTime = call("getScheduleWakeupTime", function () { return ep.getScheduleWakeupTime(id); });
    }
  }
  if (plan.refresh) r.screenRefreshNow = call("screenRefreshNow", function () { return ep.screenRefreshNow(); });
  show("wake: " + JSON.stringify(r.setScheduleWakeupTime || null));
  post("plan", r, function () {
    if (!plan.sleep_after_s) return;
    setTimeout(function () {
      lastTick = Date.now();
      post("sleep", { at: new Date().toString() }, function () {
        var s = call("goToSleep", function () { return ep.goToSleep(); });
        post("sleep-result", s);
      });
    }, plan.sleep_after_s * 1000);
  });
}

function start() {
  document.getElementById("stamp").textContent = BUILD + " " + new Date().toLocaleString();
  var info = probe();
  show("boot reason: " + JSON.stringify(info.isScheduledPlayBootReason || null));
  show("version: " + JSON.stringify(info.getVersion || null));
  post("boot", info, function () {
    var x = new XMLHttpRequest();
    x.open("GET", SERVER + "/plan?t=" + Date.now(), true);
    x.onload = function () {
      var plan = {};
      try { plan = JSON.parse(x.responseText); } catch (e) { post("plan-parse", err(e)); }
      run(plan);
    };
    x.onerror = function () { show("plan fetch failed"); };
    x.send();
  });
}

window.onload = function () {
  start();
  setInterval(heartbeat, 15000);
};
