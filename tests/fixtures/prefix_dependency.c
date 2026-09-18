static int pure(int value) { return value + 1; }
void prefix_dependency(int *a) {
    for (int i = 1; i < 64; ++i) a[i] = pure(a[i - 1]);
}
