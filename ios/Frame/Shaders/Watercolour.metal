#include <metal_stdlib>
#include <SwiftUI/SwiftUI_Metal.h>
using namespace metal;

// The new picture painted over the old one in watercolour, as the panel
// draws it (FrameDevelop). Applied to the new picture's layer; what it
// leaves transparent shows the old picture underneath.
//
// Each patch is first a wash of the colours that will be there (the new
// picture blurred, a little more saturated), with ragged edges, soft in
// some places and sharp in others, where the pigment gathers darker; the
// drawing then comes up in the wash. Lengths are in "sheet pixels": the
// picture's short side is 540 of them, as in the concept it was drawn in.

namespace paper {

float hash(float2 cell, float seed) {
    float3 p = fract(float3(cell.xyx) * 0.1031 + seed * 0.0173);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
}

/// Smooth value noise, 0…1.
float noise(float2 at, float seed) {
    float2 cell = floor(at);
    float2 f = at - cell;
    float2 u = f * f * (3.0 - 2.0 * f);
    float a = hash(cell, seed);
    float b = hash(cell + float2(1, 0), seed);
    float c = hash(cell + float2(0, 1), seed);
    float d = hash(cell + float2(1, 1), seed);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float ease(float x) {
    x = clamp(x, 0.0, 1.0);
    return x * x * (3.0 - 2.0 * x);
}

/// How far a place is from a stroke from `a` to `b`, `wide.x` wide at
/// `a` and `wide.y` at `b` (half widths); under 0 it is inside it.
float strokeAway(float2 at, float2 a, float2 b, float2 wide) {
    float2 v = b - a;
    float along = clamp(dot(at - a, v) / max(dot(v, v), 0.0001), 0.0, 1.0);
    return length(at - a - v * along) - mix(wide.x, wide.y, along);
}

/// How far a place is from a box with round corners (`box`: its left,
/// top, right and bottom); under 0 it is inside it.
float boxAway(float2 at, float4 box, float corner) {
    float2 q = abs(at - 0.5 * (box.xy + box.zw)) - 0.5 * (box.zw - box.xy) + corner;
    return length(max(q, float2(0.0))) + min(max(q.x, q.y), 0.0) - corner;
}

}  // namespace paper

[[ stitchable ]] half4 watercolour(float2 position, SwiftUI::Layer layer, float2 size, float progress) {
    using namespace paper;
    // The layer reaches past the picture by the blur's reach: paint nothing there.
    if (any(position < float2(0)) || any(position > size)) { return half4(0); }
    float unit = min(size.x, size.y) / 540.0;
    float2 q = position / unit;
    float2 n = position / size;

    // When each place is reached: patches spreading from the middle out.
    bool portrait = size.y >= size.x;
    float2 off = float2(n.x - 0.5, n.y - (portrait ? 0.47 : 0.5)) * (portrait ? float2(1.5, 1.05) : float2(1.05, 1.5));
    float order = 0.55 * (0.7 * noise(q / 120.0, 41.0) + 0.3 * noise(q / 50.0, 42.0)) + 0.45 * length(off);
    order = clamp((order - 0.14) / 0.71, 0.0, 1.0);
    float ragged = 0.6 * noise(q / 14.0, 61.0) + 0.4 * noise(q / 6.0, 62.0);
    float grain = noise(q / 2.2, 71.0);
    float wetness = noise(q / 150.0, 81.0);
    float reach = order + 0.12 * (ragged - 0.5) + 0.03 * (grain - 0.5);

    float t = progress * 1.45 - 0.22;
    float soft = 0.012 + 0.075 * wetness * wetness;
    float e = t - reach;
    float wash = ease(e / soft);
    float edge = (e - soft * 0.9) / (soft * 0.8 + 0.004);
    float rim = wash > 0.0 ? 0.2 * exp(-edge * edge) : 0.0;
    // The drawing itself, after the wash; everywhere by the end.
    float drawn = max(ease((e - 0.13) / 0.2), ease((progress - 0.9) / 0.1));
    float glaze = wash * 0.86;
    if (glaze <= 0.0 && drawn <= 0.0) { return half4(0); }

    // The wash: the new picture blurred (a 14 px Gaussian), a little more saturated.
    float sigma = 14.0 * unit;
    // Premultiplied: what lies past the picture's edge (clear) adds nothing.
    float4 sum = float4(0);
    float weights = 0;
    for (int j = -3; j <= 3; j++) {
        for (int i = -3; i <= 3; i++) {
            float2 d = float2(i, j) * 0.62;
            float w = exp(-0.5 * dot(d, d));
            float2 at = clamp(position + d * sigma, float2(0.5), size - 0.5);
            sum += float4(layer.sample(at)) * w;
            weights += w;
        }
    }
    float cover = sum.a / weights;
    float3 blurred = sum.a > 0.0 ? sum.rgb / sum.a : float3(0);
    float luma = dot(blurred, float3(0.2126, 0.7152, 0.0722));
    blurred = clamp(mix(float3(luma), blurred, 1.2), 0.0, 1.0);
    float speck = 1.0 - 0.06 * (grain - 0.5) * wash;
    float3 tint = blurred * (1.0 - rim * (1.15 - blurred)) * speck;

    float4 sharp = float4(layer.sample(position));
    // Over the old picture: the wash covers `glaze` of it, the drawing the rest.
    glaze *= cover;
    drawn *= sharp.a;
    float alpha = glaze + drawn - glaze * drawn;
    float3 colour = tint * glaze * (1.0 - drawn) + (sharp.a > 0.0 ? sharp.rgb / sharp.a : float3(0)) * drawn;
    return half4(half3(colour), half(alpha));
}

// A stop's stain in JourneyRoad: ink poured out of the stop's dot, spreading
// under its text (RoadStain; Mateusz 2026-11-11 09:11: „Plamy mają
// powstawać z kropek… Rozlewanie tuszu a nie jego rozmywanie… jakby papier
// na krawędzi plam nasiąkał tuszem i już mniej mocnym odcieniem powstaje
// fragmentami drugie halo plamy. Jakby akwarela wsiąkała w papier”). The
// layer is the field: the stain's shape, white and blurred, so its alpha
// says how deep inside the ink a place is. Ink is where the field is over
// a threshold. `age` is how long ago the ink started out of `source`, the
// dot, in seconds. It goes out from there on all sides with a sharp wet
// front, in lobes, fast at first and then slower, the far corner of the
// stain `reach` away; under `bottom`, the stain's foot, it comes late, to
// gather and drip. Where it has come it is there at once, its edge sharp;
// it creeps a little further (the threshold falls) and dries: from `wet`
// to `dense` where it lay thick, by the dot and along the edge it pooled
// at, and to `wash` where it ran thin, the paper's grain showing through.
// Then the paper at the edge soaks it up: in places a second halo grows
// out past the edge, in `seeped`, paler (`soak.x` of the page covered),
// with an edge of its own where the pigment stops (`soak.y` more there).
// `cover` is how much of the page the ink covers wet and dry, `tooth` how
// much the grain shows and how uneven it dries. Lengths are in points;
// `seed` tells one stain's ink from another's.
[[ stitchable ]] half4 spill(float2 position, SwiftUI::Layer layer, float2 source, float bottom, float reach, float age,
                             float seed, half4 wet, half4 dense, half4 wash, half4 seeped, float2 cover, float2 soak,
                             float2 tooth) {
    using namespace paper;
    float field = float(layer.sample(position).a);
    if (field <= 0.04 || age <= 0.0) { return half4(0); }
    float2 at = position;

    // When the ink gets here.
    float away = length(at - source) / max(reach, 1.0);
    float way = clamp(away + 0.24 * (noise(at / 34.0, 41.0 + seed) - 0.5) + 0.1 * (noise(at / 13.0, 43.0 + seed) - 0.5),
                      0.0, 1.1);
    float below = at.y - bottom + 2.0;
    if (below > 0.0) { way = max(way, mix(way, 1.0 + below / 60.0, smoothstep(0.0, 6.0, below))); }
    float comes = 3.8 * (1.0 - pow(1.0 - min(way, 1.48) / 1.5, 1.0 / 2.2));
    float since = age - comes;
    if (since <= 0.0) { return half4(0); }

    float ragged = 0.6 * noise(at / 9.0, 61.0 + seed) + 0.4 * noise(at / 4.0, 62.0 + seed);
    float wetness = noise(at / 60.0, 81.0 + seed);
    float grain = noise(at / 1.5, 71.0 + seed);
    float pool = noise(at / 30.0, 91.0 + seed);
    float lobe = noise(at / 24.0, 93.0 + seed);
    float patch = noise(at / 26.0, 97.0 + seed);
    float capillary = 0.6 * noise(at / 5.0, 98.0 + seed) + 0.4 * noise(at / 2.2, 99.0 + seed);
    float seep = ease(since / 0.9);
    float arrive = ease(since / 0.015);
    float dry = ease((since - 0.8) / 2.2);

    // The ink's edge: sharp.
    float edge = 0.58 - 0.13 * seep + 0.07 * (ragged - 0.5) + 0.08 * (lobe - 0.5);
    float inside = smoothstep(edge - 0.035, edge + 0.015, field);
    // The second halo: only in places, growing out of the edge as the paper soaks.
    float part = smoothstep(0.4, 0.6, patch);
    float deep = ease((since - 0.9) / 2.8) * part * (0.26 * (0.55 + 0.9 * pool) + 0.07 * (capillary - 0.5));
    float outer = edge - deep;
    float ring = deep > 0.0 ? smoothstep(0.0, 0.03, deep) * smoothstep(outer - 0.03, outer + 0.012, field) : 0.0;
    float lip = ring * (1.0 - smoothstep(outer + 0.015, outer + 0.09, field));
    float pale = ring * (soak.x + soak.y * lip) * (1.0 - 0.35 * (grain - 0.5));
    if (inside <= 0.0 && pale <= 0.0) { return half4(0); }

    float rim = dry * (1.0 - 0.7 * part) * smoothstep(edge - 0.005, edge + 0.03, field)
        * (1.0 - smoothstep(edge + 0.08, edge + 0.3, field)) * (0.45 + 0.55 * (1.0 - wetness));
    float thick = 1.0 - ease(away / 0.9);
    float body = min(1.0, 0.78 * thick + 0.7 * rim);
    float dried = min(0.97, (cover.y + 0.1 * thick + 0.08 * (pool - 0.5)) * (1.0 - tooth.x * (grain - 0.5)) + 0.12 * rim);
    float alpha = arrive * max(inside * mix(cover.x, dried, dry), pale);
    float3 settled = mix(float3(wash.rgb), float3(dense.rgb), body) + (pool - 0.5) * tooth.y * dry;
    float3 ink = mix(float3(wet.rgb), settled, dry);
    float3 colour = clamp(mix(float3(seeped.rgb), ink, inside), 0.0, 1.0);
    return half4(half3(colour * alpha), half(alpha));
}

// Where the work is now, at the end of the road in JourneyRoad: a blot of
// red watercolour (RoadBlot; Mateusz 2026-11-11 09:44: „czerwona kropka na
// końcu także jako plama akwareli, bez białego otoku. Na styku z czernią
// miesza się jak prawdziwa akwarela”). The view is a square of white with
// the blot's middle at `centre`; `age` is how long ago the blot began, in
// seconds. It spreads from its middle to about `radius`, its outline
// wandering (`lobes`: three turns of it), with a sharp wet edge; dry, its
// pigment has pooled along the rim and its middle is paler, and the paper
// round it has soaked some of it up, in places, as a paler ring. The black
// meets it in two places: the end of the line, which runs into it from
// `back`, and the last stop's ink, which comes out of it towards `into`
// and under the text there (`stain`: that line's box), `flow` seconds ago.
// While both are wet they run into each other: the red creeps out along
// the black and the black into the red's rim, more with time, the middle
// of the blot staying red. Over the black this paints the mixture; the
// line and the stain themselves are drawn under it. Lengths are in points.
//
// The same blot, smaller, is a later work's on the line that goes on into
// "Dalsze losy" (Mateusz 10:20: „kontynuację linii Drogi dzieła, tylko
// innym kolorem plam”): there the line runs through it, on to `on` (the
// blot's own middle where it does not), and what pours out of it is another
// `paint` than the line's `ink`; the red runs into both. `size`: the
// blot's radius, how far in from its rim its middle stays red, and half
// the width of the line where it comes in and where it goes on (0: it
// does not). What the paints run by is in proportion to the radius.
[[ stitchable ]] half4 blot(float2 position, half4 color, float2 centre, float2 back, float2 on, float2 into, float4 stain,
                            float4 size, float age, float flow, float seed, float3 lobes, half4 red, half4 ink,
                            half4 paint) {
    using namespace paper;
    if (age <= 0.0) { return half4(0); }
    float radius = size.x;
    float scale = radius / 10.4;
    float2 at = position;
    float2 off = at - centre;
    float away = length(off);
    float turn = atan2(off.y, off.x);
    float rim = radius * (1.0 + 0.07 * sin(2.0 * turn + lobes.x) + 0.05 * sin(3.0 * turn + lobes.y)
                          + 0.035 * sin(5.0 * turn + lobes.z));
    float ragged = 1.6 * (noise(at / 4.0, 11.0 + seed) - 0.5);
    // The black keeps to the blot's rim: its middle stays red.
    float core = rim - away - size.y;
    float line = max(core, min(strokeAway(at, back, centre, float2(size.z, size.z)),
                               strokeAway(at, centre, on, float2(size.w, size.w))));
    float poured = max(core, min(strokeAway(at, centre, into, float2(4.6, 10.0)), boxAway(at, stain, 8.0)));
    float warp = 3.2 * (noise(at / 6.0, 21.0 + seed) - 0.5) + 1.6 * (noise(at / 2.5, 22.0 + seed) - 0.5);
    float pool = noise(at / 9.0, 31.0 + seed);
    float grain = noise(at / 1.5, 41.0 + seed);
    float patch = noise(at / 12.0, 51.0 + seed);

    float grow = 1.0 - pow(1.0 - min(1.0, age / 0.55), 2.4);
    float dry = ease((age - 0.9) / 2.2);
    float soak = ease((age - 1.1) / 2.6);
    float run = ease((age - 0.5) / 2.6);
    float there = ease((flow - 0.05) / 0.3);

    // The blot itself: sharp at its edge.
    float edge = away - rim * grow + ragged * grow;
    float inside = 1.0 - smoothstep(-0.5, 0.5, edge);
    // The black here: the line, and the last stop's ink once it has come.
    float black = max(1.0 - smoothstep(-0.6, 0.6, line), (1.0 - smoothstep(-0.6, 0.6, poured)) * there);
    // How much red has run to this place, and how much black.
    float reds = max(inside, grow >= 1.0 ? 1.0 - smoothstep(0.0, 1.0 + 9.0 * scale * run, edge + scale * warp) : 0.0);
    float lined = 1.0 - smoothstep(-0.5, 0.5 + 4.0 * scale * run, line + 0.8 * scale * warp);
    float stained = (1.0 - smoothstep(-0.5, 0.5 + 4.0 * scale * run, poured + 0.8 * scale * warp)) * there;
    float blacks = max(lined, stained);
    // The paper round the blot soaks the red up, in places.
    float deep = soak * smoothstep(0.42, 0.62, patch) * scale * (3.0 + 2.6 * pool);
    float ring = deep > 0.0 ? smoothstep(0.0, 0.5, deep) * (1.0 - smoothstep(deep - 0.7, deep + 0.3, edge)) : 0.0;
    float lip = ring * smoothstep(deep - 1.5, deep - 0.4, edge);
    float pale = ring * (0.3 + 0.18 * lip) * (1.0 - 0.3 * (grain - 0.5)) * (1.0 - black);
    float alpha = max(max(inside * (0.96 - 0.05 * dry), black * smoothstep(0.02, 0.25, reds) * 0.97), pale);
    if (alpha <= 0.0) { return half4(0); }

    // The red: wet and even at first; dry, darker along the rim and paler in the middle.
    float pooled = smoothstep(-3.4, -0.9, edge) * dry;
    float shade = (1.0 - 0.17 * pooled) * (1.0 + 0.1 * (1.0 - smoothstep(-6.0, -2.0, edge)) * dry)
        * (1.0 + 0.09 * (pool - 0.5) * dry) * (1.0 - 0.1 * (grain - 0.5));
    float share = blacks / (blacks + 2.0 * reds + 0.000001);
    // What the red runs into here: the line's ink, or the paint that pours out of the blot.
    float3 other = mix(float3(ink.rgb), float3(paint.rgb), stained / (lined + stained + 0.000001));
    float3 colour = mix(min(float3(red.rgb) * shade, float3(1.0)), other, share);
    return half4(half3(colour * alpha), half(alpha));
}

// A sea the work crossed, on "Droga dzieła", as a wash (Mateusz
// 2026-11-11 11:09: „Morze - super - wdrażamy”). Applied to a white
// rectangle over the sea. `box`: the band the wash keeps to (left, top,
// right, bottom); its edge wanders in and out of it. `entry`: where the
// line comes into it; the paint floods out from there, `reach` far at the
// most. `came`: how far it has flooded (0…1.15), how dry it is, how far
// the paper round it has soaked (both 0…1), and how many points of the
// line are drawn. `line`: every `each`th point of the line, x and y by
// turns. Dry, the pigment has gathered along the edge. The line is drawn
// into the wash wet: behind the pen its ink runs out into the blue, in
// places further, and thins there to a grey. Lengths are in points.
[[ stitchable ]] half4 sea(float2 position, half4 color, float4 box, float2 entry, float reach, float4 came,
                           device const float *line, int count, float each, float seed, half4 blue, half4 deep,
                           half4 ink) {
    using namespace paper;
    float spread = came.x;
    float dry = came.y;
    float soak = came.z;
    float tip = came.w;
    if (spread <= 0.0) { return half4(0); }
    float2 at = position;
    float edge = boxAway(at, box, 26.0) + 16.0 * (noise(at / 46.0, 3.0 + seed) - 0.5)
        + 5.0 * (noise(at / 11.0, 4.0 + seed) - 0.5) + 1.4 * (noise(at / 3.0, 5.0 + seed) - 0.5);
    if (edge > 9.0) { return half4(0); }
    // The wet front, out from where the line comes in: uneven, and quicker along the sea than across it.
    float gone = length((at - entry) * float2(1.0, 1.5)) * (1.0 + 0.3 * (noise(at / 30.0, 6.0 + seed) - 0.5));
    float front = gone - spread * (reach + 30.0);
    float inside = (1.0 - smoothstep(-0.6, 0.6, edge)) * (1.0 - smoothstep(-2.5, 1.5, front));
    float pool = noise(at / 34.0, 31.0 + seed);
    float grain = noise(at / 1.5, 41.0 + seed);
    // Dry, the pigment has pooled along the edge; wet, there is more of it just behind the front.
    float rim = smoothstep(-5.0, -0.6, edge) * dry;
    float wet = (1.0 - dry) * smoothstep(-14.0, -1.0, front) * 0.16;
    float alpha = inside * (0.3 * (1.0 + 0.5 * (pool - 0.5)) * (1.0 - 0.34 * (grain - 0.5)) + 0.2 * rim + wet);
    float3 colour = mix(float3(blue.rgb), float3(deep.rgb), 0.5 * rim + 0.25 * (pool - 0.5));
    // The paper past the edge soaks a little of it up, in places.
    if (inside < 1.0 && soak > 0.0) {
        float sunk = soak * smoothstep(0.45, 0.62, noise(at / 14.0, 51.0 + seed)) * (3.0 + 3.0 * pool);
        float ring = sunk > 0.0 ? (1.0 - smoothstep(sunk - 0.8, sunk + 0.3, edge)) * smoothstep(-0.5, 0.5, edge) : 0.0;
        alpha = max(alpha, ring * 0.12);
    }
    // The line in the wet wash: how near this place is to it, and how long ago the pen passed there.
    if (inside > 0.0 && tip > 0.0 && count >= 4) {
        float near = 1.0e9;
        float where = 0.0;
        for (int k = 0; k + 3 < count; k += 2) {
            float2 a = float2(line[k], line[k + 1]);
            float2 v = float2(line[k + 2], line[k + 3]) - a;
            float along = clamp(dot(at - a, v) / max(dot(v, v), 0.0001), 0.0, 1.0);
            float away = length(at - a - v * along);
            if (away < near) {
                near = away;
                where = (float(k / 2) + along) * each;
            }
        }
        float passed = tip - where;
        if (passed > 0.0 && near < 24.0) {
            float run = ease(passed / 80.0);
            float bloom = smoothstep(0.38, 0.7, noise(at / 22.0, 23.0 + seed));
            float wide = 1.5 + run * (3.0 + 9.0 * bloom);
            float warp = 7.0 * (noise(at / 9.0, 21.0 + seed) - 0.5) + 3.0 * (noise(at / 3.4, 22.0 + seed) - 0.5);
            float feather = near + warp * run * (0.4 + 0.6 * bloom);
            // Close to the line the black is strong; further out it thins to a grey in the blue.
            float black = (1.0 - smoothstep(1.4, 1.4 + wide, feather)) * min(1.0, passed / 6.0) * inside;
            float strong = black * black * (3.0 - 2.0 * black) * (1.0 - 0.2 * dry);
            colour = mix(colour, float3(ink.rgb), strong * 0.72);
            alpha = alpha + (0.66 - alpha) * strong;
        }
    }
    alpha = clamp(alpha, 0.0, 1.0);
    return half4(half3(colour * alpha), half(alpha));
}
