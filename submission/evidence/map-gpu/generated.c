#include "runtime.h"

#pragma omp declare target
static int apply(int value) { return value * 3 + 1; }
#pragma omp end declare target

static void kernel(const int * restrict input, int * restrict output, int n) {
    {
if ((n) > 0) {
#pragma omp target teams distribute parallel for map(to: input[0:n]) map(tofrom: output[0:n]) firstprivate(n)
for (int i = 0; i < n; ++i) {
        output[i] = apply(input[i]);
    }
}
}
}
int main(int argc, char **argv) { return harness(argc, argv, kernel, 0, NULL); }
