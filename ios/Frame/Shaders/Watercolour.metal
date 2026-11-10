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

// A pale white underpainting spreading on the page (JourneyRoad's
// WashPaint), as the wash above spreads over the old picture: from its
// middle out, patch by patch, with a ragged front, soft in some places and
// sharp in others. The front is thick with paint, and the paint behind it
// is wet and whiter; it dries to the pale stain the layer holds. Lengths
// are in points: `centre` is the stain's middle and `radii` how far it
// reaches sideways and up and down; `seed` tells one stain from another.
[[ stitchable ]] half4 stain(float2 position, SwiftUI::Layer layer, float2 centre, float2 radii, float progress, float seed) {
    using namespace paper;
    float4 there = float4(layer.sample(position));
    if (progress >= 1.0) { return half4(there); }
    if (progress <= 0.0) { return half4(0); }

    // When each place is reached.
    float away = length((position - centre) / (radii * 1.25));
    float order = 0.3 * (0.7 * noise(position / 45.0, 41.0 + seed) + 0.3 * noise(position / 18.0, 42.0 + seed)) + 0.7 * away;
    order = clamp((order - 0.1) / 0.8, 0.0, 1.0);
    float ragged = 0.6 * noise(position / 9.0, 61.0 + seed) + 0.4 * noise(position / 4.0, 62.0 + seed);
    float grain = noise(position / 1.5, 71.0 + seed);
    float wetness = noise(position / 60.0, 81.0 + seed);
    float reach = order + 0.12 * (ragged - 0.5) + 0.03 * (grain - 0.5);

    float t = progress * 1.3 - 0.08;
    float soft = 0.012 + 0.075 * wetness * wetness;
    float e = t - reach;
    float wash = ease(e / soft);
    // The front, a thin line of thick paint, and the wet paint behind it;
    // both gone as the stain dries at the end.
    float off = e - soft * 0.5;
    float front = exp(-off * off / (0.014 * 0.014));
    float wet = e > 0.0 ? 0.55 * exp(-e / 0.22) : 0.0;
    float thick = min(1.0, max(front, wet * wash)) * (1.0 - ease((progress - 0.82) / 0.18));
    // Only inside the stain itself, not in the soft edge round it.
    thick *= 0.95 * smoothstep(0.15, 0.35, there.a);

    float4 dried = there * wash;
    return half4(float4(thick) + dried * (1.0 - thick));
}
