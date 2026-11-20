/* The scan of three, for whoever is no C++: the phone's Swift, a test.
 * `server/src/frame_server/imaging/reflections.py` is what it does and why. */
#ifndef FRAME_SCAN_H
#define FRAME_SCAN_H

#ifdef __cplusplus
extern "C" {
#endif

/* What a merge came to (`Merged` there), and what its time went on. */
typedef struct frame_scan_note {
    int used;       /* side photographs that could be laid over the first */
    double removed; /* the share of the first's light within the work taken off */
    int doubt;      /* the photographs do not show one flat work in one light */
    /* Seconds: the files read, each part of the merge, the file written. */
    double read, laid, own, layer, mended, whole, written;
} frame_scan_note;

/* `first` without the reflections the `count` photographs of `sides` do
 * not share, within `corners` (the work: x and y of its top left, top
 * right, bottom right and bottom left, 0–1 across and down), written to
 * `into`. All of them .npy files, rows × columns × 3 of 8 bits, RGB.
 * `anyway`: also of photographs that show no one flat work. Zero when it
 * went well; else what went wrong is said in `error`. */
int frame_scan_merge_files(const char* first, const char* const* sides, int count, const double* corners,
                           int anyway, const char* into, frame_scan_note* note, char* error, int error_size);

/* The photograph at `path` (.npy, rows × columns × 3 of 8 bits, RGB) in
 * the colours a colour chart gives it, in place: `tables` the file the
 * server gives of the chart it read (`colorchecker.tables`). Done to each
 * of a scan's photographs before `frame_scan_merge_files`. Zero when it
 * went well; else what went wrong is said in `error`, and the file is as
 * it was. */
int frame_scan_chart_file(const char* path, const char* tables, char* error, int error_size);

/* How a lens bends what it draws is said by the one measured term `k1`
 * about the photograph's middle, or (`count` above 0) by the camera's own
 * `table` of `count` values about the lens's middle (`centre_x`,
 * `centre_y`: 0–1 across and down the photograph): `imaging/lens.py`
 * `Bend` on the server, which tells the phone which.
 *
 * The picture at `path` (.npy, rows × columns × 3 of 8 bits) as a lens
 * without that bend would have drawn it, in place: the server's
 * `lens.straight`. Zero when it went well; else what went wrong is said in
 * `error`, and the file is as it was. */
int frame_scan_straight_file(const char* path, double k1, const double* table, int count, double centre_x,
                             double centre_y, char* error, int error_size);

/* The same of `pixels` (rows × columns × 3 bytes, a row after another), in
 * place: what the phone shows of a photograph. */
int frame_scan_straight_pixels(unsigned char* pixels, int rows, int columns, double k1, const double* table,
                               int count, double centre_x, double centre_y, char* error, int error_size);

/* `points` (x and y of each of `many`, 0–1 across and down a photograph of
 * `columns` by `rows`) set on the photograph as taken, put where they are
 * on it straightened (`lens.moved`); `back` not zero: set on it
 * straightened, put where they are on it as taken (`lens.bent`). In place. */
int frame_scan_lens_points(double* points, int many, int columns, int rows, double k1, const double* table,
                           int count, double centre_x, double centre_y, int back, char* error, int error_size);

/* A scene made up (a work under glass, a lamp in it, photographed three
 * times), `side` pixels long, merged: nothing is read or written. For a
 * test, and to time a phone without a scan at hand. */
int frame_scan_made_up(int side, frame_scan_note* note, char* error, int error_size);

/* A museum photograph cut down to the work by the phone's model (`Kadr`),
 * with no Claude: `server/src/frame_server/imaging/crop_model.py`.
 *
 * `pixels` (rows × columns × 3 bytes, RGB, a row after another) as the
 * model takes it, into `into`: 3 × `side` × `side` floats 0–255, a colour
 * after another, the photograph shrunk into the middle of black; `box`:
 * its left, top, width and height there. Zero when it went well. */
int frame_crop_letterbox(const unsigned char* pixels, int rows, int columns, int side, float* into, int* box,
                         char* error, int error_size);

/* What the model's answer about `pixels` comes to: `logits` its `masks`
 * (2 × `side` × `side`: the work, the frame or passe-partout around it,
 * before the sigmoid), `sure` its `cut`. The work's corners set on the
 * photograph's edges into `work`, the outer edge around it into
 * `surround` (x and y of the top left, top right, bottom right and bottom
 * left, 0–1 across and down); `found`: 1 when there is a work, 2 when
 * there is a surround (both: 3). 1 cut it, 0 it wants no cut, 2 unsure
 * (left whole, for the owner); -1 when it went wrong (said in `error`). */
int frame_crop_find(const unsigned char* pixels, int rows, int columns, const float* logits, int side, double sure,
                    double* work, double* surround, int* found, char* error, int error_size);

/* No more threads than these from now on (0: as many as there are cores). */
void frame_scan_threads(int threads);

/* What the core was built of, in a line. */
const char* frame_scan_built(void);

#ifdef __cplusplus
}
#endif

#endif
