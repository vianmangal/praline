extern int mystery(int value);
static int apply(int value) { return mystery(value); }
void unknown_call(int n, const int *restrict input, int *restrict output) {
    for (int i = 0; i < n; ++i) output[i] = apply(input[i]);
}
