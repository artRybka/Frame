// Loaded from the server by the signed app. Reports that remote code runs, then
// acts as a remote console: polls /cmd ({"id": n, "code": "...", "async": bool})
// and posts what the code evaluates to (or passes to done()) as "cmd-result".
(function () {
  var v = null;
  try { v = webapis.epaper.getVersion(); } catch (e) { v = "error: " + e; }
  post("remote-js", { loaded: true, epaper_version: v });

  function safe(value, depth) {
    depth = depth || 0;
    if (value === undefined) return "(undefined)";
    if (value === null || typeof value !== "object") return typeof value === "function" ? "(function)" : value;
    if (depth > 4) return "(deep)";
    var out = Array.isArray(value) ? [] : {};
    for (var k in value) {
      try { out[k] = safe(value[k], depth + 1); } catch (e) { out[k] = "(error " + e + ")"; }
    }
    return out;
  }

  var seen = -1;  // the first poll only records the current id: never replay after a restart
  function deliver(id, value) { post("cmd-result", { id: id, value: safe(value) }); }
  function poll() {
    var x = new XMLHttpRequest();
    x.open("GET", SERVER + "/cmd?t=" + Date.now(), true);
    x.onload = function () {
      var c = null;
      try { c = JSON.parse(x.responseText); } catch (e) { c = null; }
      if (c && seen < 0) {
        seen = c.id;
      } else if (c && c.id > seen) {
        seen = c.id;
        var id = c.id;
        var done = function (value) { deliver(id, value); };
        try {
          var r = eval(c.code);
          if (!c.async) deliver(id, r);
        } catch (e) {
          deliver(id, { thrown: err(e) });
        }
      }
      setTimeout(poll, 2000);
    };
    x.onerror = function () { setTimeout(poll, 5000); };
    x.send();
  }
  poll();
})();
