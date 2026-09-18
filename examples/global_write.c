#include "runtime.h"
static int counter = 0;
static int apply(int value) { counter += 1; return value * 3 + 1; }
static void kernel(const int * restrict input, int * restrict output, int n) {
    for (int i = 0; i < n; ++i) {
        output[i] = apply(input[i]);
    }
}
int main(int argc, char **argv) { return harness(argc, argv, kernel, 1, &counter); }
