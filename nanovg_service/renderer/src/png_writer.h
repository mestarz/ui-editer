#ifndef PNG_WRITER_H
#define PNG_WRITER_H
#include <stddef.h>
/* Encodes RGBA8 image to PNG memory; caller frees with free().
   Returns 0 on success. */
int png_encode_rgba(const unsigned char *pixels, int w, int h, int stride_bytes,
                    unsigned char **out_buf, size_t *out_len);
#endif
