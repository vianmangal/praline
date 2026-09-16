static int square(int value) { return value * value + 3; }
static int apply(int value) { return square(value) - 1; }
void helper_map(int n, const int *restrict input, int *restrict output) {
    for (int i = 0; i < n; ++i) {
        output[i] = apply(input[i]);
    }
}
