/* Test-only execution adapter: checks every element and untouched sentinels. */
#include <stdio.h>
#include <stdlib.h>
#ifndef KERNEL
#define KERNEL helper_map
#endif
#ifndef SCALE
#define SCALE 0
#endif
void KERNEL(int n, const int *restrict input, int *restrict output);
int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 1024;
    unsigned seed = argc > 2 ? (unsigned)atoi(argv[2]) : 1;
    if (n < 0 || n > 1000000) return 3;
    int *input = malloc((n + 8) * sizeof(*input));
    int *output = malloc((n + 8) * sizeof(*output));
    if (!input || !output) return 4;
    for (int i = 0; i < n + 8; ++i) {
        seed = seed * 1664525u + 1013904223u;
        input[i] = (int)(seed % 101u) - 50;
        output[i] = -777;
    }
    KERNEL(n, input, output);
    for (int i = 0; i < n + 8; ++i) {
        int expected = i >= n ? -777 : (SCALE ? input[i] * 3 + 1 : input[i] * input[i] + 2);
        if (output[i] != expected) {
            fprintf(stderr, "mismatch at %d: %d != %d\n", i, output[i], expected);
            return 1;
        }
    }
    puts("all elements match");
    free(input); free(output);
    return 0;
}
