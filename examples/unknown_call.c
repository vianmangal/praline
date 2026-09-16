#include "runtime.h"
#include <math.h>
/* Library semantics are deliberately outside the compiler's supported subset. */
static int apply(int value) { return (int)fabs((double)value) * 3 + 1; }
static void kernel(const int * restrict input, int * restrict output, int n) {
    for (int i = 0; i < n; ++i) {
        output[i] = apply(input[i]);
    }
}
int main(int argc, char **argv) { return harness(argc, argv, kernel, 0, NULL); }
