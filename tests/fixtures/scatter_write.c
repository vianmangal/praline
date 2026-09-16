static int pure(int value) { return value * 2; }
void scatter_write(int n, const int *restrict input, int *restrict output) {
    for (int i = 0; i < n; ++i) output[i % 2] = pure(input[i]);
}
