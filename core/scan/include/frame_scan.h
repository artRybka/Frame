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

/* A scene made up (a work under glass, a lamp in it, photographed three
 * times), `side` pixels long, merged: nothing is read or written. For a
 * test, and to time a phone without a scan at hand. */
int frame_scan_made_up(int side, frame_scan_note* note, char* error, int error_size);

/* No more threads than these from now on (0: as many as there are cores). */
void frame_scan_threads(int threads);

/* What the core was built of, in a line. */
const char* frame_scan_built(void);

#ifdef __cplusplus
}
#endif

#endif
