#include "runtime.h"
static int apply(int value) { return value * 3 + 1; }
static void kernel(const int *input, int *output, int n) {
    for (int i = 0; i < n; ++i) {
        output[i] = apply(input[i]);
    }
}
int main(int argc, char **argv) { return harness(argc, argv, kernel, 0, NULL); }
