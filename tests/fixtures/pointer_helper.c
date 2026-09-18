static void store(int *destination, const int *source, int slot) {
    destination[slot] = source[slot] * 3 + 1;
}
static void apply(int *out, const int *in, int index) {
    store(out, in, index);
}
void pointer_helper(int n, const int *restrict input, int *restrict output) {
    for (int i = 0; i < n; ++i) apply(output, input, i);
}
