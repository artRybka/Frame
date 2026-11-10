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

// The pale white underpainting of JourneyRoad coming onto the page from
// the top and soaking into it (RoadWash). The layer is the field: the
// stains under the texts and the runs of paint between them, white and
// blurred, so its alpha says how deep inside the paint a place is. Paint
// is where the field is over a threshold. `front` is how far down the road
// the paint has come and `done` how far it has dried, both heights on the
// road; `origin` is the road's corner in the layer. At the front the paint
// has only just arrived: thin, wet and whiter, and only in the middle of
// its stain. Behind the front the threshold falls, so the paint seeps out
// to its edge; it sinks into the paper (the grain shows through and the
// wet white goes pale) and gathers whiter along the edge as it dries.
// Above `done` it is dry and stays as it is. Lengths are in points; `seed`
// tells one road's paint from another's.
[[ stitchable ]] half4 soak(float2 position, SwiftUI::Layer layer, float2 origin, float front, float done, float seed) {
    using namespace paper;
    float field = float(layer.sample(position).a);
    if (field <= 0.02) { return half4(0); }
    float2 at = position - origin;

    // When the paint gets here: from the top, sooner in some patches.
    float ragged = 0.6 * noise(at / 9.0, 61.0 + seed) + 0.4 * noise(at / 4.0, 62.0 + seed);
    float reached = at.y + 8.0 + 40.0 * (noise(at / 70.0, 41.0 + seed) - 0.5) + 5.0 * (ragged - 0.5);
    float e = front - reached;
    if (e <= 0.0) { return half4(0); }
    float u = e / max(front - done, 26.0);
    float seep = ease(u * 0.9);
    float arrive = ease(u * 2.2);
    float wetness = noise(at / 60.0, 81.0 + seed);

    // The edge: soft where the paper was wet, sharp where it was dry.
    float edge = 0.82 - 0.32 * seep + 0.06 * (ragged - 0.5);
    float feather = 0.02 + 0.1 * wetness * wetness + 0.1 * (1.0 - seep);
    float inside = smoothstep(edge - feather, edge + 0.015, field);
    if (inside <= 0.0) { return half4(0); }

    float grain = noise(at / 1.5, 71.0 + seed);
    float pool = noise(at / 38.0, 91.0 + seed);
    // A second, smaller wash over the middle of each stain.
    float second = 0.2 * smoothstep(0.80, 0.88, field + 0.1 * (noise(at / 22.0, 95.0 + seed) - 0.5));
    float body = 0.44 * (0.85 + 0.3 * pool) * (1.0 - 0.3 * (grain - 0.5) * seep);
    float rim = 0.34 * seep * smoothstep(edge - 0.005, edge + 0.02, field) * (1.0 - smoothstep(edge + 0.03, edge + 0.1, field))
        * (0.35 + 0.65 * (1.0 - wetness));
    float wet = u < 1.0 ? 0.4 * (1.0 - ease(u * 1.1)) : 0.0;
    float alpha = inside * arrive * min(1.0, body + second * seep + rim + wet);
    // White, premultiplied.
    return half4(half(alpha));
}
