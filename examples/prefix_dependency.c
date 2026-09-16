#include "runtime.h"
static int apply(int value) { return value + 1; }
static void kernel(const int *input, int *output, int n) {
    (void)input;
    for (int i = 1; i < n; ++i) {
        output[i] = apply(output[i - 1]);
    }
}
int main(int argc, char **argv) { return harness(argc, argv, kernel, 2, NULL); }
