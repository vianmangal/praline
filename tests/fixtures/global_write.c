static int counter = 0;
static int bump(int value) { ++counter; return value + 1; }
void global_write(int n, const int *restrict input, int *restrict output) {
    for (int i = 0; i < n; ++i) output[i] = bump(input[i]);
}
