static int pure(int value) { return value + 1; }
void alias_unknown(int n, const int *input, int *output) {
    for (int i = 0; i < n; ++i) output[i] = pure(input[i]);
}
