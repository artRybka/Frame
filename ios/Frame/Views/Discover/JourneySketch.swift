import Foundation

/// The small pen drawings by "Droga dzieła" (Mateusz 2026-11-11 20:02:
/// „odręcznych rysunków dla ważnych miejsc dla obrazu. Alby symboli monet
/// przy sprzedaży. Chodzi o proste, piórkiem kilka kresek np. Paryż - wieża
/// Eiffla. Sprzedaż - monety… w stylu obecnego rysunku drogi… okazjonalnie a
/// nie przy każdym Punkcie”; 21:18: „Zdarzenia i miejsca od razu”): what
/// there is to draw, which stops get a drawing, where it has room, and the
/// nib that draws it. A drawing is a few strokes in a box of 100, made by
/// the road's own pen held smaller: thin across, full down, each stroke
/// coming down thin, pressed, lifted thin.
///
/// Which drawing a stop gets is read off the stop as the server has always
/// sent it (its kind, its place, its year), so a road worked out long ago
/// is as complete as a new one (21:19: „Stare drogi - trzeba przerobić aby
/// miały kompletność jak nowotworzone”).
enum JourneySketch {
    enum Motif: String, CaseIterable, Sendable {
        // What happened to the work.
        case easel, frame, scroll, coins, gavel, gift, ship, trunk, helmet, emptyframe, brush, museum
        // Where it was.
        case eiffel, notredame, bigben, liberty, fuji, canal, windmill, colosseum, gondola, duomo, brandenburg
        case stephansdom, capitol, skyline, onion, zygmunt, mariacki, frauenkirche, pyramids, parthenon, bell
    }

    /// One stroke as it was drawn in the box of 100: through its points as
    /// a curve (`smooth`) or straight from one to the next; `light`: how
    /// hard the pen was pressed, 1 the most.
    struct Stroke: Equatable, Sendable {
        var points: [CGPoint]
        var smooth: Bool
        var light: CGFloat
    }

    static func strokes(_ motif: Motif) -> [Stroke] { drawn[motif] ?? [] }

    private static let drawn: [Motif: [Stroke]] = source.mapValues(read)

    /// "s0.8:22,99 33,80;z1:50,12 50,0": strokes apart by ";", each its
    /// manner (s: a curve, z: straight), its `light`, and its points.
    static func read(_ text: String) -> [Stroke] {
        text.split(separator: ";").compactMap { part in
            let halves = part.split(separator: ":")
            guard halves.count == 2, let manner = halves[0].first, let light = Double(halves[0].dropFirst()) else { return nil }
            let points = halves[1].split(separator: " ").compactMap { pair -> CGPoint? in
                let both = pair.split(separator: ",")
                guard both.count == 2, let x = Double(both[0]), let y = Double(both[1]) else { return nil }
                return CGPoint(x: x, y: y)
            }
            return points.count >= 2 ? Stroke(points: points, smooth: manner == "s", light: CGFloat(light)) : nil
        }
    }

    /// The drawings. Made as sketches first (sketches 32 and 33) and
    /// written out from them: a long straight side is several strokes, the
    /// pen lifted at each corner and each a little long, as a hand does.
    static let source: [Motif: String] = [
        .easel: "z1:22.6,14 74.9,14;z1:74,12.2 74,66.8;z1:75,64 24,64;z1:26,64.6 26,11.5;z1:50,4 50,14;z1:30,64 16,98;z1:70,64 84,98;z0.8:50,64 50,92;z0.8:20,68 80,68;s0.5:34,52 42,38 50,46 58,30 66,40",
        .frame: "z1:50,2 28,24;z1:50,2 72,24;z1:11.2,24 88.2,24;z1:86,20.9 86,93.4;z1:88.6,92 11.7,92;z1:14,94.2 14,22.1;z0.7:20,33 80.3,33;z0.7:77,31.1 77,85.5;z0.7:77.7,83 20.4,83;z0.7:23,85.4 23,29.5;s0.5:28,76 40,58 48,68 58,50 72,76;s0.5:66,44 65.5,46 64,47.5 62,48 60,47.5 58.5,46 58,44 58.5,42 60,40.5 62,40 64,40.5 65.5,42 66,44",
        .scroll: "s1:22,16 26,10 74,10 78,16 74,21 26,21 22,16;z1:27,21 27,80;z1:73,21 73,80;s1:27,80 50,85 73,80;s0.5:35,33 50,32 65,33;s0.5:35,43 50,42 65,43;s0.5:35,53 46,52 57,53;s0.9:59,62 61.7,62.5 63.9,64.1 65.5,66.3 66,69 65.5,71.7 63.9,73.9 61.7,75.5 59,76 56.3,75.5 54.1,73.9 52.5,71.7 52,69 52.5,66.3 54.1,64.1 56.3,62.5 59,62;z0.8:55,75 51,91;z0.8:63,75 66,91",
        .coins: "s1:11,52 11.7,50 13.7,48.1 16.9,46.4 21.2,45 26.3,43.9 32,43.2 38,43 44,43.2 49.7,43.9 54.8,45 59.1,46.4 62.3,48.1 64.3,50 65,52 64.3,54 62.3,55.9 59.1,57.6 54.8,59 49.7,60.1 44,60.8 38,61 32,60.8 26.3,60.1 21.2,59 16.9,57.6 13.7,55.9 11.7,54 11,52;z1:11,52 11,84;z1:65,52 65,84;s0.8:11,62.5 11.2,63.5 11.7,64.5 12.5,65.5 13.7,66.4 15.1,67.3 16.9,68.1 18.9,68.9 21.2,69.5 23.6,70.1 26.3,70.6 29.1,71 32,71.3 35,71.4 38,71.5 41,71.4 44,71.3 46.9,71 49.7,70.6 52.4,70.1 54.8,69.5 57.1,68.9 59.1,68.1 60.9,67.3 62.3,66.4 63.5,65.5 64.3,64.5 64.8,63.5 65,62.5;s0.8:11,73 11.2,74 11.7,75 12.5,76 13.7,76.9 15.1,77.8 16.9,78.6 18.9,79.4 21.2,80 23.6,80.6 26.3,81.1 29.1,81.5 32,81.8 35,81.9 38,82 41,81.9 44,81.8 46.9,81.5 49.7,81.1 52.4,80.6 54.8,80 57.1,79.4 59.1,78.6 60.9,77.8 62.3,76.9 63.5,76 64.3,75 64.8,74 65,73;s1:11,84 11.2,85 11.7,86 12.5,87 13.7,87.9 15.1,88.8 16.9,89.6 18.9,90.4 21.2,91 23.6,91.6 26.3,92.1 29.1,92.5 32,92.8 35,92.9 38,93 41,92.9 44,92.8 46.9,92.5 49.7,92.1 52.4,91.6 54.8,91 57.1,90.4 59.1,89.6 60.9,88.8 62.3,87.9 63.5,87 64.3,86 64.8,85 65,84;s1:65.8,75.1 65.1,71.9 65.1,68.5 65.7,65.2 67.1,62.2 69,59.5 71.4,57.4 74.2,55.9 77.3,55.1 80.4,55.1 83.5,55.8 86.3,57.2 88.8,59.3 90.8,61.9 92.2,64.9 92.9,68.1 92.9,71.5 92.3,74.8 90.9,77.8 89,80.5 86.6,82.6 83.8,84.1 80.7,84.9 77.6,84.9 74.5,84.2 71.7,82.8 69.2,80.7 67.2,78.1 65.8,75.1;s0.6:75,64 83,67 76,72 83,77;s0.5:28,51 38,48.5 48,51",
        .gavel: "z1:19.5,30.4 44.9,11.3;z1:42.4,10 59.1,31.4;z1:59.2,29.1 32.2,49.4;z1:35.1,49.5 19.1,28.9;z1:45,34 86,78;z0.5:24,26 38,44;z0.5:40,16 54,34;z0.9:5.1,84 54.6,84;z0.9:52,82.8 52,96.2;z0.9:54.1,94 4.9,94;z0.9:8,96.7 8,82.6;s0.5:60,20 66,14;s0.5:66,28 74,26;s0.5:54,10 56,2",
        .gift: "z1:11,44 87.4,44;z1:86,42.3 86,96.5;z1:86.6,94 12.1,94;z1:14,95 14,43.1;z0.9:7.3,32 94.8,32;z0.9:92,31.1 92,45.2;z0.9:93.7,44 4.9,44;z0.9:8,44.7 8,30.2;z0.8:50,32 50,94;s1:50,30 36,10 24,14 30,26 50,30;s1:50,30 64,10 76,14 70,26 50,30",
        .ship: "s1:6,62 12,76 20,82 76,82 88,74 96,58;z0.8:6,62 96,58;z0.8:30,61.8 30,45;z0.8:29.1,48 71.2,45.9;z0.8:70,43.6 70,62.3;z1:40,49.2 40,26.3;z1:36.6,28 47.6,28;z1:47,24.9 47,48.4;z1:56,46.9 56,29.1;z1:54.6,30 65.9,30;z1:63,29 63,48.2;s0.6:44,24 50,16 44,10 54,4 66,8;s0.6:2,92 12,88 22,92 32,88 42,92 52,88 62,92 72,88 82,92 92,88 99,91;z0.5:18,66 24,66;z0.5:36,66 42,66;z0.5:54,65 60,65;z0.5:72,64 78,64",
        .trunk: "z1:8.8,40 92.3,40;z1:90,38.7 90,89.8;z1:90.9,88 6.8,88;z1:10,89.6 10,38.1;z0.8:10,54 90,54;z0.7:29,40 29,88;z0.7:71,40 71,88;s1:40,40 42,29 58,29 60,40;s0.8:50,55 51.8,55.8 52.9,57.8 52.9,60.2 51.8,62.2 50,63 48.2,62.2 47.1,60.2 47.1,57.8 48.2,55.8 50,55",
        .helmet: "s1:20,62 23,38 50,25 77,38 80,62;s1:9,65 50,73 91,65;z1:20,62 9,65;z1:80,62 91,65;s0.6:27,68 50,92 73,68;s0.5:34,40 50,33 66,40",
        .emptyframe: "s0.9:50,4 51.4,4.6 52,6 51.4,7.4 50,8 48.6,7.4 48,6 48.6,4.6 50,4;z1:19.9,19.6 92.1,33.6;z1:89.2,31.3 76.1,99;z1:78.7,96.2 7.9,82.5;z1:9.6,84.9 22.3,19.5;z0.7:27.5,30.2 79.4,40.3;z0.7:78.5,39.6 69,88.1;z0.7:70.6,85.5 18.6,75.4;z0.7:20,78.4 29.7,28.5;z0.7:50,8 35.9,22.7;z0.7:50,8 75.2,30.3;z0.5:6,30 12,24;z0.5:2,44 9,42;z0.5:92,14 97,9",
        .brush: "z1:82,8 45,53;z1:90,15 53,60;z0.8:82,8 90,15;z0.8:45,53 53,60;z0.8:39,58 48,66;z1:45,53 39,58;z1:53,60 48,66;s1:39,58 28,72 17,91;s1:48,66 36,80 17,91;s0.5:40,68 30,80;s0.8:4,96 22,91 40,95 56,92",
        .museum: "z1:3.9,41.2 51.4,15.2;z1:48.1,15 94.6,40.3;z0.9:6,40 94,40;z1:18,45 18,84;z1:39,45 39,84;z1:61,45 61,84;z1:82,45 82,84;z0.9:8,86 92,86;z0.8:2,93 98,93;s0.5:44,33 50,29 56,33",
        .eiffel: "s1:22,99 33,80 40,60 45,38 48.5,12;s1:78,99 67,80 60,60 55,38 51.5,12;z1:50,12 50,0;s1:27,76 50,74.5 73,76;s0.9:40,50 50,49 60,50;s0.8:31,99 38,86 50,81 62,86 69,99;z0.6:37,74 56,52;z0.6:63,74 44,52",
        .notredame: "z1:14,99.5 14,21;z1:11.5,22 38.7,22;z1:38,19.9 38,99.6;z1:62,98.7 62,20;z1:61.4,22 87.8,22;z1:86,21.3 86,98.8;z0.9:38,46 62,46;s0.9:40,98 41,80 50,72 59,80 60,98;s0.8:50,50 51.8,50.2 53.5,50.8 55,51.7 56.3,53 57.2,54.5 57.8,56.2 58,58 57.8,59.8 57.2,61.5 56.3,63 55,64.3 53.5,65.2 51.8,65.8 50,66 48.2,65.8 46.5,65.2 45,64.3 43.7,63 42.8,61.5 42.2,59.8 42,58 42.2,56.2 42.8,54.5 43.7,53 45,51.7 46.5,50.8 48.2,50.2 50,50;z0.6:20,98 20,78;z0.6:32,98 32,78;z0.6:68,98 68,78;z0.6:80,98 80,78;z0.6:22,40 22,28;z0.6:30,40 30,28;z0.6:70,40 70,28;z0.6:78,40 78,28;z0.6:50,46 50,14;z0.7:6,98 94,98",
        .bigben: "z1:38,98 38,34;z1:62,98 62,34;z1:35,36.3 35,13.7;z1:34.5,15 66.8,15;z1:65,13.4 65,36.2;z1:68.4,34 32.4,34;s0.8:50,18 52.5,18.5 54.6,19.9 56,22 56.5,24.5 56,27 54.6,29.1 52.5,30.5 50,31 47.5,30.5 45.4,29.1 44,27 43.5,24.5 44,22 45.4,19.9 47.5,18.5 50,18;z0.6:50,24.5 50,20;z0.6:50,24.5 54,26.5;z1:36.8,16.7 51.4,-3.9;z1:48.5,-4.1 62.4,15.5;z0.5:46,46 46,90;z0.5:54,46 54,90;z0.8:28,98 72,98",
        .liberty: "z1:32.6,102.1 37.6,76.9;z1:34,80 66.1,80;z1:62.7,78.7 67.3,101.7;s1:41,80 41,62 45,46;s1:60,80 60,60 56,46;s0.6:49,76 51,62 49,50;s0.9:50.5,32 52.4,32.5 54,33.8 55.1,35.7 55.5,38 55.1,40.3 54,42.2 52.4,43.5 50.5,44 48.6,43.5 47,42.2 45.9,40.3 45.5,38 45.9,35.7 47,33.8 48.6,32.5 50.5,32;z0.6:46,32 42,25;z0.6:50.5,31 50.5,22;z0.6:55,32 59,25;s1:45,46 38,32 34,16;s0.7:34,16 30,9 34,2 38,9 34,16;z0.8:54.5,49.4 67.1,46.2;z0.8:63.5,43.7 66.1,60.9;z0.8:67,59.8 56.8,62.3;z0.8:58.2,63.2 55.7,47.1",
        .fuji: "s1:2,90 22,66 35,40 42,24;s1:42,24 47,21.5 52,24 57,21.5;s1:57,21.5 65,40 79,66 98,90;z0.6:31,46 38,52 44,43 50,54 56,44 62,51 68,46;s0.7:82.6,12.1 85.7,12.2 88.6,13.4 90.7,15.7 91.9,18.6 91.8,21.7 90.6,24.6 88.3,26.7 85.4,27.9 82.3,27.8 79.4,26.6 77.3,24.3 76.1,21.4 76.2,18.3 77.4,15.4 79.7,13.3 82.6,12.1;s0.6:0,96 28,93 62,97 100,94",
        .canal: "z1:10,99.2 10,39.2;z1:6.9,42 18.9,42;z1:16,43.7 16,32.3;z1:15.2,34 23.4,34;z1:21,34.7 21,25.3;z1:19.9,26 28,26;z1:27,24.5 27,34.7;z1:26.5,34 33,34;z1:32,33.2 32,43.6;z1:31.4,42 40.1,42;z1:37,96 37,36;s1:37,36 40,31 42,19 50,11 58,19 60,31 63,36;z1:63,36 63,96;z1:61.7,47.9 76.5,26.2;z1:75.3,26 89.9,47.3;z1:89,46 89,96;z0.6:19,52 19,64;z0.6:29,52 29,64;z0.6:19,74 19,88;z0.6:29,74 29,88;z0.6:45,42 45,54;z0.6:55,42 55,54;z0.6:45,62 45,74;z0.6:55,62 55,74;z0.8:50,82 50,96;z0.6:71,56 71,68;z0.6:81,56 81,68;z0.6:76,78 76,92;s0.6:4,101 15.5,97 27,101 38.5,97 50,101 61.5,97 73,101 84.5,97 96,101",
        .windmill: "z1:39,96 45,48;z1:61,96 55,48;s1:43,48 50,39 57,48;z0.8:42,48 58,48;z1:20,12 80,72;z1:80,12 20,72;z0.5:26,10 40,24;z0.5:74,10 60,24;z0.5:26,74 40,60;z0.5:74,74 60,60;z0.7:50,82 50,96;s0.7:18,96 50,98 82,96",
        .colosseum: "s1:6,52 20,36 50,30 80,38 94,56;z1:6,52 6,90;z1:94,56 94,90;s1:6,90 50,96 94,90;s0.7:6,70 50,77 94,72;s0.7:14,66 18.5,53 23,66;s0.7:30,66 34.5,53 39,66;s0.7:46,66 50.5,53 55,66;s0.7:62,66 66.5,53 71,66;s0.7:78,66 82.5,53 87,66;s0.7:14,89 18.5,77 23,89;s0.7:30,89 34.5,77 39,89;s0.7:46,89 50.5,77 55,89;s0.7:62,89 66.5,77 71,89;s0.7:78,89 82.5,77 87,89",
        .gondola: "s1:4,56 20,72 50,77 80,72 95,54;s0.7:6,58 30,67 70,67 93,57;z1:95,54 98,40;s0.9:4,56 1,47 6,42;z1:30,66 30,45;s0.8:30,36 31.3,36.3 32.5,37.2 33.2,38.5 33.5,40 33.2,41.5 32.5,42.8 31.3,43.7 30,44 28.7,43.7 27.5,42.8 26.8,41.5 26.5,40 26.8,38.5 27.5,37.2 28.7,36.3 30,36;z0.8:17,30 45,86;s0.6:0,92 12.2,88 24.5,92 36.8,88 49,92 61.2,88 73.5,92 85.8,88 98,92",
        .duomo: "s1:22,58 26,34 50,17 74,34 78,58;s0.6:40,58 42,34 50,17;s0.6:60,58 58,34 50,17;z1:46,18.6 46,8.1;z1:43,9 57.5,9;z1:54,7.1 54,19;z1:50,9 50,1;z1:18,58 82,58;z1:22,58 22,74;z1:78,58 78,74;z1:13,74 87,74;z1:15,74 15,96;z1:85,74 85,96;s0.6:36,63 37.8,63.6 38.9,65.1 38.9,66.9 37.8,68.4 36,69 34.2,68.4 33.1,66.9 33.1,65.1 34.2,63.6 36,63;s0.6:50,63 51.8,63.6 52.9,65.1 52.9,66.9 51.8,68.4 50,69 48.2,68.4 47.1,66.9 47.1,65.1 48.2,63.6 50,63;s0.6:64,63 65.8,63.6 66.9,65.1 66.9,66.9 65.8,68.4 64,69 62.2,68.4 61.1,66.9 61.1,65.1 62.2,63.6 64,63;z0.8:8,96 92,96",
        .brandenburg: "z1:8,30 92,30;z1:8,40 92,40;z1:8,30 8,40;z1:92,30 92,40;z1:26,30.8 26,19.2;z1:24.5,20 75.3,20;z1:74,17 74,31;z1:50,20 50,7;s0.7:40,15 50,10 60,15;z1:14,43 14,90;z1:28,43 28,90;z1:42,43 42,90;z1:58,43 58,90;z1:72,43 72,90;z1:86,43 86,90;z0.8:4,92 96,92",
        .stephansdom: "z1:28,96 28,46;z1:44,96 44,46;z1:27.9,46.6 36.6,-1.3;z1:35.6,-0.1 44.2,46.9;z0.6:31,32 41,32;z0.8:29,46 43,46;z1:43.1,65.9 53.2,43.5;z1:50.9,44 93.4,44;z1:89.3,41 95.6,66.5;z1:44,64 95,64;z0.6:54,60 59,48 65,60 71,48 77,60 83,48 88,60;z1:95,64 95,96;z0.6:56,74 56,90;z0.6:69,74 69,90;z0.6:82,74 82,90;z0.8:20,96 99,96",
        .capitol: "s1:34,44 36,27 50,17 64,27 66,44;z1:47,18.3 47,7.4;z1:46,9 55.8,9;z1:53,6.9 53,19.8;z1:50,9 50,2;z1:31,44 69,44;z1:34,44 34,56;z1:66,44 66,56;z0.6:42,47 42,54;z0.6:50,47 50,54;z0.6:58,47 58,54;z1:9,56 91,56;z1:11,56 11,84;z1:89,56 89,84;z0.7:21,62 21,80;z0.7:31,62 31,80;z0.7:41,62 41,80;z0.7:50,62 50,80;z0.7:59,62 59,80;z0.7:69,62 69,80;z0.7:79,62 79,80;z1:4,84 96,84;z0.7:1,92 99,92",
        .skyline: "z1:8,97.5 8,50.8;z1:5.1,52 27.5,52;z1:24,55.1 24,25.1;z1:21,28 42.7,28;z1:40,26.8 40,46.1;z1:38.4,44 54.6,44;z1:54,44.6 54,28.7;z1:52.7,30 60.6,30;z1:58,33.4 58,16.2;z1:54.7,18 71.5,18;z1:68,14.6 68,31.6;z1:66.8,30 73.2,30;z1:72,28.9 72,57.1;z1:69.6,56 93.2,56;z1:90,53 90,97.9;z1:32,28 32,12;z0.5:14,60 14,67;z0.5:18,74 18,81;z0.5:30,38 30,45;z0.5:34,56 34,63;z0.5:46,54 46,61;z0.5:62,28 62,35;z0.5:64,48 64,55;z0.5:80,64 80,71;z0.5:84,78 84,85;z0.5:47,72 47,79;z0.5:30,76 30,83;s0.6:2,101 14,97 26,101 38,97 50,101 62,97 74,101 86,97 98,101",
        .onion: "z1:44,96 44,50;z1:56,96 56,50;s1:44,50 40.6,41 45.8,31 50,16 54.2,31 59.4,41 56,50;s0.5:45,44 50,38 55,44;z1:50,16 50,4;z0.7:46.5,9 53.5,9;z1:19,96 19,66;z1:33,96 33,66;s1:19,66 15.1,57 21.1,47 26,38 30.9,47 36.9,57 33,66;s0.5:20,60 26,54 32,60;z0.8:26,38 26,29;z1:67,96 67,66;z1:81,96 81,66;s1:67,66 63.1,57 69.1,47 74,38 78.9,47 84.9,57 81,66;s0.5:68,60 74,54 80,60;z0.8:74,38 74,29;z0.8:10,96 90,96",
        .zygmunt: "z1:46,84 47,36;z1:54,84 53,36;z1:42,36 58,36;z1:32.5,84 67.9,84;z1:65,83.2 65,101.5;z1:68.2,99 32.2,99;z1:35,101.8 35,82.1;s1:50,36 49,27 50,19;s0.8:50,11.5 51.8,12.2 52.9,13.9 52.9,16.1 51.8,17.8 50,18.5 48.2,17.8 47.1,16.1 47.1,13.9 48.2,12.2 50,11.5;z1:42,34 42,3;z0.8:37.5,10 46.5,10;z0.7:49,24 42,22;z0.7:52,26 60,33",
        .mariacki: "z1:24,96 24,36;z1:42,96 42,36;z1:23.7,37 33.8,1.2;z1:32.6,2.6 42.8,38.8;z0.6:25,27 41,27;z0.6:27,21 27,31;z0.6:39,21 39,31;z1:58,96 58,50;z1:76,96 76,50;s1:58,50 60,40 67,33 74,40 76,50;z0.8:67,33 67,24;z1:39.9,64.7 51.1,50.7;z1:48.9,50.7 60.1,64.6;s0.8:46,96 46,84 50,80 54,84 54,96;z0.6:33,48 33,60;z0.6:33,70 33,84;z0.6:67,60 67,74;z0.8:16,96 84,96",
        .frauenkirche: "z1:27,96 27,38;z1:43,96 43,38;s1:27,38 25.5,29 35,19 44.5,29 43,38;z0.8:35,19 35,10;z1:57,96 57,38;z1:73,96 73,38;s1:57,38 55.5,29 65,19 74.5,29 73,38;z0.8:65,19 65,10;z1:42.5,64.7 50.3,54.6;z1:47.9,52.3 58.5,65.9;z0.6:35,48 35,60;z0.6:65,48 65,60;z0.6:35,70 35,84;z0.6:65,70 65,84;z0.8:50,76 50,96;z0.8:18,96 82,96",
        .pyramids: "z1:6.7,92.3 42.5,29.1;z1:41.6,29.2 76.5,90.8;z0.6:42,30 54,90;z1:68.4,68.8 81.4,45.4;z1:79.6,47.1 99.2,92.7;s0.8:2,90 50,92 99,90;s0.7:20,15 22.7,15.5 24.9,17.1 26.5,19.3 27,22 26.5,24.7 24.9,26.9 22.7,28.5 20,29 17.3,28.5 15.1,26.9 13.5,24.7 13,22 13.5,19.3 15.1,17.1 17.3,15.5 20,15",
        .parthenon: "z1:14.8,37.4 52.3,21;z1:48.6,21.4 84,36.9;z0.9:17,36 83,36;z0.9:24,40 24,63;z0.9:34,40 34,63;z0.9:44,40 44,63;z0.9:56,40 56,63;z0.9:66,40 66,63;z0.9:76,40 76,63;z1:15,66 85,66;z0.8:11,72 89,72;s0.7:0,97 18,82 50,77 82,82 100,97",
        .bell: "z1:25.9,12 75.3,12;z1:72,10.2 72,24.1;z1:75,21 26.9,21;z1:28,22.3 28,10.6;s1:41,21 38,48 27,76;s1:59,21 62,48 73,76;s1:23,78 50,85 77,78;z1:27,76 23,78;z1:73,76 77,78;z0.7:52,46 49,57 54,66 50,82;s0.9:50,87 52.4,87.8 53.8,89.8 53.8,92.2 52.4,94.2 50,95 47.6,94.2 46.2,92.2 46.2,89.8 47.6,87.8 50,87",
    ]

    // MARK: Which stops get one

    /// A stop of the road, as much of it as says what to draw.
    struct Stop: Equatable, Sendable {
        var place: String
        var lat: Double
        var lon: Double
        /// "1900", "1884–1886", "przed 1891", "ok. 1830–1832".
        var year: String
        /// made, shown, home, inherited, sold, gift, travel, war, stolen, restored, museum.
        var kind: String
        var text: String
        var detour: Bool
    }

    /// A drawing on the road: by stop `stop`, or (`sea`) on the sea the
    /// work crossed to get there.
    struct Pick: Equatable, Sendable {
        var stop: Int
        var motif: Motif
        var sea = false
    }

    /// The year a stop is told under, when it is plain: "przed 1905" is no
    /// year (a sight built in 1886 may not have stood yet).
    static func year(_ text: String) -> Int? {
        let low = text.lowercased()
        if low.contains("przed") || low.contains("before") { return nil }
        var digits = ""
        for character in low {
            if character.isASCII, character.isNumber {
                digits.append(character)
                if digits.count == 4 { return Int(digits) }
            } else if !digits.isEmpty {
                digits = ""
            }
        }
        return nil
    }

    /// A place with a sight everyone knows it by: within `reach` km of it,
    /// or, a stop without coordinates, named so; `since`: the year the
    /// sight has stood from (nil: as good as always), `before`: what was
    /// drawn there until then.
    private struct Sight: Sendable {
        var motif: Motif
        var lat: Double
        var lon: Double
        var reach: Double
        var names: [String]
        var since: Int? = nil
        var before: Motif? = nil
    }

    private static let sights: [Sight] = [
        Sight(motif: .eiffel, lat: 48.86, lon: 2.35, reach: 25, names: ["paryż", "paris"], since: 1889, before: .notredame),
        Sight(motif: .bigben, lat: 51.51, lon: -0.13, reach: 30, names: ["londyn", "london"], since: 1859),
        Sight(motif: .liberty, lat: 40.71, lon: -74.0, reach: 30, names: ["nowy jork", "new york"], since: 1886),
        Sight(motif: .canal, lat: 52.37, lon: 4.9, reach: 12, names: ["amsterdam"]),
        Sight(motif: .windmill, lat: 52.08, lon: 4.31, reach: 12, names: ["haga", "hague"]),
        Sight(motif: .windmill, lat: 52.01, lon: 4.36, reach: 8, names: ["delft"]),
        Sight(motif: .windmill, lat: 52.16, lon: 4.49, reach: 10, names: ["lejda", "leiden"]),
        Sight(motif: .windmill, lat: 52.38, lon: 4.64, reach: 8, names: ["haarlem"]),
        Sight(motif: .windmill, lat: 51.92, lon: 4.48, reach: 12, names: ["rotterdam"]),
        Sight(motif: .windmill, lat: 52.09, lon: 5.12, reach: 12, names: ["utrecht"]),
        Sight(motif: .colosseum, lat: 41.9, lon: 12.5, reach: 20, names: ["rzym", "rome", "roma"]),
        Sight(motif: .gondola, lat: 45.44, lon: 12.33, reach: 12, names: ["wenecj", "venice", "venezia"]),
        Sight(motif: .duomo, lat: 43.77, lon: 11.26, reach: 12, names: ["florencj", "florence", "firenze"], since: 1436),
        Sight(motif: .brandenburg, lat: 52.52, lon: 13.4, reach: 25, names: ["berlin"], since: 1791),
        Sight(motif: .stephansdom, lat: 48.21, lon: 16.37, reach: 20, names: ["wiedeń", "wiedn", "vienna", "wien"]),
        Sight(motif: .capitol, lat: 38.9, lon: -77.04, reach: 20, names: ["waszyngton", "washington"], since: 1866),
        Sight(motif: .skyline, lat: 41.88, lon: -87.63, reach: 30, names: ["chicago"], since: 1890),
        Sight(motif: .onion, lat: 55.75, lon: 37.62, reach: 30, names: ["moskw", "moscow"], since: 1561),
        Sight(motif: .zygmunt, lat: 52.23, lon: 21.01, reach: 20, names: ["warszaw", "warsaw"], since: 1644),
        Sight(motif: .mariacki, lat: 50.06, lon: 19.94, reach: 15, names: ["krak"]),
        Sight(motif: .frauenkirche, lat: 48.14, lon: 11.58, reach: 20, names: ["monachium", "munich", "münchen"], since: 1525),
        Sight(motif: .parthenon, lat: 37.98, lon: 23.73, reach: 20, names: ["ateny", "athens"]),
        Sight(motif: .bell, lat: 39.95, lon: -75.17, reach: 25, names: ["filadelfi", "philadelphia"], since: 1753),
        Sight(motif: .pyramids, lat: 30.0, lon: 31.2, reach: 60, names: ["kair", "cairo", "giza", "egipt"]),
        Sight(motif: .pyramids, lat: 25.7, lon: 32.64, reach: 60, names: ["luksor", "luxor", "teby"]),
        Sight(motif: .fuji, lat: 35.36, lon: 138.73, reach: 420, names: ["edo", "tokio", "tokyo", "kioto", "kyoto", "japoni"]),
    ]

    private static func km(_ lat: Double, _ lon: Double, _ sight: Sight) -> Double {
        let r = Double.pi / 180
        let h = pow(sin((sight.lat - lat) * r / 2), 2)
            + cos(lat * r) * cos(sight.lat * r) * pow(sin((sight.lon - lon) * r / 2), 2)
        return 2 * 6371 * asin(min(1, sqrt(h)))
    }

    /// The sight of the place a stop is at, if the place has one and it
    /// stood in the stop's year: the Eiffel tower from 1889 on, Notre-Dame
    /// before; a stop without a plain year gets only what has always stood.
    static func sight(_ stop: Stop) -> Motif? {
        let found: Sight?
        if stop.lat != 0 || stop.lon != 0 {
            found = sights.filter { km(stop.lat, stop.lon, $0) <= $0.reach }
                .min { km(stop.lat, stop.lon, $0) / $0.reach < km(stop.lat, stop.lon, $1) / $1.reach }
        } else {
            let name = stop.place.lowercased()
            found = name.isEmpty ? nil : sights.first { sight in sight.names.contains { name.contains($0) } }
        }
        guard let found else { return nil }
        guard let since = found.since else { return found.motif }
        guard let year = year(stop.year) else { return found.before }
        return year >= since ? found.motif : found.before
    }

    /// What happened at a stop, as a drawing: coins for a sale (the hammer
    /// for one at auction), a ship for a journey over a sea.
    static func event(_ stop: Stop, sea: Bool) -> Motif? {
        switch stop.kind {
        case "made": return .easel
        case "shown": return .frame
        case "inherited": return .scroll
        case "sold":
            let text = stop.text.lowercased()
            return text.contains("aukcj") || text.contains("licytac") ? .gavel : .coins
        case "gift": return .gift
        case "travel": return sea ? .ship : .trunk
        case "war": return .helmet
        case "stolen": return .emptyframe
        case "restored": return .brush
        case "museum": return .museum
        default: return nil
        }
    }

    /// How much a drawing tells: a sale, a theft or a war more than a
    /// museum, which the road's red blot stands for already.
    private static func weight(_ motif: Motif) -> Double {
        switch motif {
        case .coins, .gavel, .gift, .emptyframe, .helmet, .scroll, .brush, .trunk: 2
        case .easel: 1.5
        case .frame, .museum: 1
        default: 0
        }
    }

    /// The drawings of a road: few (three on a long road, one on a short
    /// one), never at two stops next to each other, none twice, none at a
    /// side trip. The first sight of a place comes first, then what
    /// happened; a second place counts for less than a sale, so a road is
    /// not all towers. A sea the work crossed gets one ship.
    static func picks(_ stops: [Stop], seas: [Bool]) -> [Pick] {
        let most = min(3, (stops.count + 1) / 2)
        guard most > 0, stops.count > 1 else { return [] }
        var picks: [Pick] = []
        var used = Set<Motif>()
        var placed = false
        func neighbour(_ index: Int) -> Bool { picks.contains { !$0.sea && abs($0.stop - index) <= 1 } }
        // Each place's sight belongs to the stop the work first came there at.
        var sightAt: [Int: Motif] = [:]
        var seen = Set<Motif>()
        for (index, stop) in stops.enumerated() where !stop.detour {
            if let motif = sight(stop), seen.insert(motif).inserted { sightAt[index] = motif }
        }
        let crossing = stops.indices.first { $0 > 0 && $0 < seas.count && seas[$0] }
        while picks.count < most {
            var best: (pick: Pick, weight: Double)?
            func offer(_ pick: Pick, _ weight: Double) {
                guard weight > 0, !used.contains(pick.motif) else { return }
                if best == nil || weight > best!.weight { best = (pick, weight) }
            }
            for (index, stop) in stops.enumerated() where !stop.detour && !neighbour(index) {
                if let motif = sightAt[index] { offer(Pick(stop: index, motif: motif), placed ? 1.8 : 3) }
                if let motif = event(stop, sea: index < seas.count && seas[index]), motif != .ship {
                    offer(Pick(stop: index, motif: motif), weight(motif))
                }
            }
            if let crossing { offer(Pick(stop: crossing, motif: .ship, sea: true), 2.5) }
            guard let best else { break }
            picks.append(best.pick)
            used.insert(best.pick.motif)
            if sightAt[best.pick.stop] == best.pick.motif, !best.pick.sea { placed = true }
        }
        return picks.sorted { ($0.stop, $0.sea ? 0 : 1) < ($1.stop, $1.sea ? 0 : 1) }
    }

    // MARK: Where one has room

    /// How big a drawing is: the side of its box, in points.
    static let side: CGFloat = 46
    /// How far a drawing keeps from the line, and from everything else.
    static let clear: (line: CGFloat, other: CGFloat) = (10, 7)

    /// The parts of `lines` between `top` and `bottom`, each run of
    /// neighbouring points a line of its own.
    static func within(_ lines: [[CGPoint]], top: CGFloat, bottom: CGFloat) -> [[CGPoint]] {
        var out: [[CGPoint]] = []
        for line in lines {
            var run: [CGPoint] = []
            for point in line {
                if point.y >= top, point.y <= bottom {
                    run.append(point)
                } else if !run.isEmpty {
                    out.append(run)
                    run = []
                }
            }
            if !run.isEmpty { out.append(run) }
        }
        return out
    }

    /// Whether `box` is free: on the road, clear of its `lines` (the road,
    /// its side trips' branches, the line going on) and of everything `taken`.
    static func free(_ box: CGRect, lines: [[CGPoint]], taken: [CGRect], width: CGFloat, height: CGFloat) -> Bool {
        guard box.minX >= 4, box.maxX <= width - 4, box.minY >= 2, box.maxY <= height - 2 else { return false }
        let wide = box.insetBy(dx: -clear.other, dy: -clear.other)
        if taken.contains(where: { $0.intersects(wide) }) { return false }
        let far = box.insetBy(dx: -clear.line, dy: -clear.line)
        for line in lines {
            if line.count == 1, far.contains(line[0]) { return false }
            for (a, b) in zip(line, line.dropFirst()) {
                // Between two points of a line too: they may be far apart.
                let steps = max(1, Int(hypot(b.x - a.x, b.y - a.y) / 4))
                for step in 0...steps {
                    let t = CGFloat(step) / CGFloat(steps)
                    if far.contains(CGPoint(x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t)) { return false }
                }
            }
        }
        return true
    }

    /// Room for a drawing beside a stop's stain: the free place nearest to
    /// it, level with it rather than over or under; none: no drawing there.
    static func room(beside stain: CGRect, lines: [[CGPoint]], taken: [CGRect], width: CGFloat, height: CGFloat) -> CGRect? {
        let top = stain.minY - side * 0.6, bottom = stain.maxY - side * 0.4
        let near = within(lines, top: top - 2 * clear.line, bottom: bottom + side + 2 * clear.line)
        var best: (box: CGRect, cost: CGFloat)?
        var y = top
        while y <= bottom {
            var x: CGFloat = 4
            while x <= width - 4 - side {
                let box = CGRect(x: x, y: y, width: side, height: side)
                let gapX: CGFloat = max(0, stain.minX - box.maxX, box.minX - stain.maxX)
                let gapY: CGFloat = max(0, stain.minY - box.maxY, box.minY - stain.maxY)
                // Beside the stain and near it; off its middle counts a little.
                let cost: CGFloat = hypot(gapX, 2 * gapY) + 0.15 * abs(box.midY - stain.midY)
                if gapX + gapY > 0, cost < (best?.cost ?? 150), free(box, lines: near, taken: taken, width: width, height: height) {
                    best = (box, cost)
                }
                x += 5
            }
            y += 5
        }
        return best?.box
    }

    /// Room for the ship on a sea: in its band, where the line is furthest.
    static func room(on sea: CGRect, lines: [[CGPoint]], taken: [CGRect], width: CGFloat, height: CGFloat) -> CGRect? {
        let near = within(lines, top: sea.minY - 60, bottom: sea.maxY + 60)
        let points = near.flatMap { $0 }
        var best: (box: CGRect, far: CGFloat)?
        var y = sea.minY + 8
        while y <= sea.maxY - 8 - side {
            var x = max(4, sea.minX + 10)
            while x <= min(width - 4, sea.maxX - 10) - side {
                let box = CGRect(x: x, y: y, width: side, height: side)
                if free(box, lines: near, taken: taken, width: width, height: height) {
                    let middle = CGPoint(x: box.midX, y: box.midY)
                    let far: CGFloat = points.map { hypot($0.x - middle.x, $0.y - middle.y) }.min() ?? 0
                    if far > (best?.far ?? 0) + 1 { best = (box, far) }
                }
                x += 6
            }
            y += 6
        }
        return best?.box
    }

    /// A drawing on the road: whose stop's clock it is drawn by (`sea`: the
    /// ship on the sea before that stop), where, and its strokes laid out.
    struct Drawn: Equatable, Sendable {
        var stop: Int
        var sea: Bool
        var box: CGRect
        var lines: [Line]
    }

    // MARK: The nib

    /// The pen's width and the hairline round each stroke, in points, and
    /// how the nib is held: as the road's (`JourneyRoad.nibTilt`).
    static let nib: CGFloat = 2.0
    static let hair: CGFloat = 0.6
    static let tilt: CGFloat = -8 * .pi / 180
    /// A drawing takes this long and this much more for each point of its
    /// strokes' length, and no longer than `most`.
    static let pace: (least: CGFloat, each: CGFloat, most: CGFloat) = (0.5, 0.004, 2.2)

    /// A stroke on the page: its middle line, a point every half point;
    /// how hard it was pressed; and the hand's waver across it.
    struct Line: Equatable, Sendable {
        var way: [CGPoint]
        var light: CGFloat
        var phase: CGFloat
        var sway: CGFloat
        var wave: CGFloat

        var length: CGFloat { CGFloat(max(0, way.count - 1)) * 0.5 }
    }

    /// A drawing laid out in `box`, stroke by stroke in the order the pen
    /// makes them; the same hand for the same `seed`.
    static func lines(_ motif: Motif, in box: CGRect, seed: String) -> [Line] {
        var random = SeededRandom(seed + "sketch" + motif.rawValue)
        return strokes(motif).compactMap { stroke in
            let through = stroke.smooth ? curve(stroke.points) : stroke.points
            let way = even(through.map { CGPoint(x: box.minX + $0.x * box.width / 100, y: box.minY + $0.y * box.width / 100) }, step: 0.5)
            let line = Line(way: way, light: stroke.light, phase: 6.28 * random.unit(),
                            sway: 0.12 + 0.18 * random.unit(), wave: 9 + 7 * random.unit())
            return way.count >= 3 ? line : nil
        }
    }

    /// A curve through the points (Catmull-Rom).
    static func curve(_ points: [CGPoint], per: Int = 14) -> [CGPoint] {
        guard points.count >= 3 else { return points }
        let all = [points[0]] + points + [points[points.count - 1]]
        var out: [CGPoint] = []
        for i in 1..<(all.count - 2) {
            let p0 = all[i - 1], p1 = all[i], p2 = all[i + 1], p3 = all[i + 2]
            for step in 0..<per {
                let t = CGFloat(step) / CGFloat(per), t2 = t * t, t3 = t2 * t
                func at(_ a: CGFloat, _ b: CGFloat, _ c: CGFloat, _ d: CGFloat) -> CGFloat {
                    0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (3 * b - a - 3 * c + d) * t3)
                }
                out.append(CGPoint(x: at(p0.x, p1.x, p2.x, p3.x), y: at(p0.y, p1.y, p2.y, p3.y)))
            }
        }
        out.append(points[points.count - 1])
        return out
    }

    /// A point every `step` along the way.
    static func even(_ points: [CGPoint], step: CGFloat) -> [CGPoint] {
        guard var last = points.first else { return [] }
        var out = [last], left = step
        for (a, b) in zip(points, points.dropFirst()) {
            let length: CGFloat = hypot(b.x - a.x, b.y - a.y)
            guard length > 0 else { continue }
            var at: CGFloat = 0
            while length - at >= left {
                at += left
                last = CGPoint(x: a.x + (b.x - a.x) * at / length, y: a.y + (b.y - a.y) * at / length)
                out.append(last)
                left = step
            }
            left -= length - at
        }
        if let end = points.last, hypot(end.x - last.x, end.y - last.y) > step / 3 { out.append(end) }
        return out
    }

    /// A stroke's outline, drawn as far as `part` of its length: the nib
    /// held at its slant, so the stroke is thin where it runs along the
    /// nib's edge and full across it; thin where the pen came down and
    /// where it was lifted.
    static func outline(_ line: Line, part: CGFloat = 1) -> [CGPoint] {
        let end = line.way.count - 1
        guard end >= 2, part > 0 else { return [] }
        let upto = min(end, max(2, Int((CGFloat(end) * part).rounded())))
        let dx = cos(tilt) * nib / 2 * line.light, dy = sin(tilt) * nib / 2 * line.light
        var one: [CGPoint] = [], other: [CGPoint] = []
        for j in 0...upto {
            let before = line.way[max(0, j - 1)], after = line.way[min(end, j + 1)]
            let step = max(1e-6, hypot(after.x - before.x, after.y - before.y))
            let across = CGPoint(x: -(after.y - before.y) / step, y: (after.x - before.x) / step)
            // The hand is not a ruler: a slow waver, none at the stroke's ends.
            let waver = line.sway * sin(line.phase + CGFloat(j) * 0.5 / line.wave * 6.28)
                * min(1, CGFloat(j) / 6, CGFloat(end - j) / 6)
            let x = line.way[j].x + across.x * waver, y = line.way[j].y + across.y * waver
            let press = sqrt(sin(.pi * (0.06 + 0.88 * CGFloat(j) / CGFloat(end))))
            one.append(CGPoint(x: x + dx * press, y: y + dy * press))
            other.append(CGPoint(x: x - dx * press, y: y - dy * press))
        }
        return one + other.reversed()
    }

    /// How long the pen takes over a drawing.
    static func takes(_ lines: [Line]) -> CGFloat {
        min(pace.most, pace.least + pace.each * lines.reduce(0) { $0 + $1.length })
    }

    /// The drawing `age` seconds after the pen began it: each stroke's
    /// outline as far as it has come, one stroke after another. Before it
    /// began there is nothing; after `takes` all of it.
    static func outlines(_ lines: [Line], age: CGFloat) -> [[CGPoint]] {
        guard age > 0 else { return [] }
        let total = lines.reduce(0) { $0 + $1.length }
        guard total > 0 else { return [] }
        var done = total * min(1, age / takes(lines))
        var out: [[CGPoint]] = []
        for line in lines {
            guard done > 0 else { break }
            out.append(outline(line, part: min(1, done / max(line.length, 0.5))))
            done -= line.length
        }
        return out
    }
}
