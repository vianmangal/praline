#ifndef PRALINE_RUNTIME_H
#define PRALINE_RUNTIME_H
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>

/* Explicit execution adapter, not a compiler analysis rule.
   Reference computation does not call the program's kernel or helper. */
typedef void (*kernel_fn)(const int *, int *, int);
static int input_value(int i, unsigned seed) {
    return (int)(((uint32_t)i * 1664525u + seed * 1013904223u) % 1000u);
}
static double seconds(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(3);
    return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}
static int parse_number(const char *text, unsigned long limit, unsigned long *value) {
    char *end = NULL;
    errno = 0;
    unsigned long parsed = strtoul(text, &end, 10);
    if (errno || !text[0] || text[0]=='-' || *end || parsed > limit) return 0;
    *value = parsed;
    return 1;
}
static int harness(int argc, char **argv, kernel_fn kernel, int kind, int *counter) {
    unsigned long count = 1024, seed_value = 1;
    if (argc > 4 || (argc > 1 && !parse_number(argv[1], 4194304ul, &count)) ||
        (argc > 2 && !parse_number(argv[2], 4294967295ul, &seed_value))) return 2;
    int n = (int)count;
    unsigned seed = (unsigned)seed_value;
    const char *mode = argc > 3 ? argv[3] : "validate";
    if (strcmp(mode,"validate") && strcmp(mode,"reference") && strcmp(mode,"benchmark")) return 2;
    int *input = malloc((size_t)(n ? n : 1) * sizeof(int));
    int *output = calloc((size_t)(n ? n : 1), sizeof(int));
    if (!input || !output) { free(input); free(output); return 3; }
    for (int i=0; i<n; ++i) input[i] = input_value(i,seed);
    if (counter) *counter = 0;
    double start = seconds();
    if (!strcmp(mode,"reference")) {
        for (int i=0; i<n; ++i) {
            int x = input_value(i,seed);
            if (kind == 2) output[i] = i ? output[i-1] + 1 : x;
            else if (kind == 3) output[i%2] = 3*x + 1;
            else if (kind == 4) output[i] = x*x + 1;
            else output[i] = 3*x + 1;
        }
        if (counter) *counter = n;
    } else if (kind == 2) {
        memcpy(output, input, (size_t)n*sizeof(int));
        kernel(output, output, n);
    } else kernel(input, output, n);
    double elapsed = seconds()-start;
    struct timespec resolution;
    if (clock_getres(CLOCK_MONOTONIC, &resolution)) return 3;
    double timer_resolution = (double)resolution.tv_sec + (double)resolution.tv_nsec/1e9;
    uint64_t checksum = 1469598103934665603ull;
    for (int i=0; i<n; ++i) checksum = (checksum ^ (uint32_t)output[i]) * 1099511628211ull;
    printf("{\"protocol\":\"praline-output-v1\",\"size\":%d,\"seed\":%u,\"kernel_seconds\":%.12g,\"checksum\":\"%llu\",\"observables\":{\"counter\":%d}", n,seed,elapsed,(unsigned long long)checksum,counter ? *counter : 0);
    printf(",\"timer_resolution_seconds\":%.12g", timer_resolution);
    if (strcmp(mode,"benchmark")) {
        printf(",\"outputs\":[");
        for (int i=0; i<n; ++i) printf("%s%d",i ? "," : "",output[i]);
        printf("]");
    }
    printf("}\n");
    free(input); free(output); return 0;
}
#endif
