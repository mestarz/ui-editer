#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"
#include "png_writer.h"
#include <stdlib.h>
#include <string.h>

struct membuf { unsigned char *data; size_t len; size_t cap; };

static void mem_write(void *ctx, void *data, int size) {
    struct membuf *mb = (struct membuf *)ctx;
    if (mb->len + (size_t)size > mb->cap) {
        size_t ncap = mb->cap ? mb->cap * 2 : 4096;
        while (ncap < mb->len + (size_t)size) ncap *= 2;
        unsigned char *nd = (unsigned char *)realloc(mb->data, ncap);
        if (!nd) return;
        mb->data = nd; mb->cap = ncap;
    }
    memcpy(mb->data + mb->len, data, (size_t)size);
    mb->len += (size_t)size;
}

int png_encode_rgba(const unsigned char *pixels, int w, int h, int stride_bytes,
                    unsigned char **out_buf, size_t *out_len) {
    struct membuf mb = {0};
    int ok = stbi_write_png_to_func(mem_write, &mb, w, h, 4, pixels, stride_bytes);
    if (!ok) { free(mb.data); return -1; }
    *out_buf = mb.data;
    *out_len = mb.len;
    return 0;
}
