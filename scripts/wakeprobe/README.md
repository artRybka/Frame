# WakeProbe

Testowa aplikacja Tizen dla trybu Custom ramki (eksperyment E16, wyniki
w [docs/WAKE.md](../../docs/WAKE.md#aplikacja-custom-budzik-działa-e16-2026-10-28)).
Przy starcie wysyła na serwer `getVersion`, `isScheduledPlayBootReason` i resztę
getterów `webapis.epaper`, pobiera `plan.json`, ustawia budzik
`setScheduleWakeupTime` i po `sleep_after_s` usypia ramkę `goToSleep()`.
Wznowienie po pobudce wykrywa po przerwie w liczniku i zaczyna kolejny cykl
(do `cycles`).

1. Adres serwera jest wpisany na sztywno w `main.js` (`SERVER`) i `index.html`
   (sygnał `<img>`): zmień go na adres komputera w sieci ramki.
2. `scripts/wakeprobe/pack.sh 1.0.0`: buduje i podpisuje paczkę profilem
   certyfikatu Samsunga `frame` (Tizen Studio, poziom Partner, DUID ramki),
   zapisuje `dist/wakeprobe/WakeProbe.wgt` i `sssp_config.xml`.
3. `echo '{"wake_in_s": 180, "sleep_after_s": 30, "cycles": 3}' > dist/wakeprobe/plan.json`,
   potem `python3 scripts/wakeprobe/server.py` (port 3000). Raporty trafiają
   do `dist/wakeprobe/requests.log`.
4. Ramka: Content source → Custom, adres `http://<komputer>:3000/app`
   (albo MDC `0xC7 82 <url>`, a potem `0xC7 81 01`, co od razu instaluje).
   W Developer mode da się też `tizen install -n WakeProbe.wgt -s <ip>:26101`
   i `tizen run -p FrmWake001.WakeProbe -s <ip>:26101`.
