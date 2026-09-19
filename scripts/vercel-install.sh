#!/usr/bin/env bash
set -euo pipefail

# Vercel's Python runtime does not ship Clang. Install it in the Amazon Linux
# build image, then copy the executable and its non-system libraries into the
# function bundle.
dnf install -y clang >/dev/null

vendor_root="$PWD/vendor"
rm -rf "$vendor_root"
mkdir -p "$vendor_root/bin" "$vendor_root/lib" "$vendor_root/libexec"

clang_path="$(command -v clang)"
cp -L "$clang_path" "$vendor_root/libexec/clang-real"

while read -r library; do
  [ -f "$library" ] || continue
  case "$library" in
    /lib64/libc.so.*|/lib64/libm.so.*|/lib64/libpthread.so.*|/lib64/libdl.so.*|/lib64/librt.so.*|/lib64/ld-linux-*.so.*|/lib64/libgcc_s.so.*|/lib64/libstdc++.so.*)
      ;;
    *) cp -L "$library" "$vendor_root/lib/" ;;
  esac
done < <(ldd "$clang_path" | awk '/=> \/|^\// { for (i=1; i<=NF; i++) if ($i ~ /^\//) print $i }' | sort -u)

resource_dir="$(clang -print-resource-dir)"
cp -R "$resource_dir" "$vendor_root/resource"

cat > "$vendor_root/bin/clang" <<'EOF'
#!/usr/bin/env sh
vendor_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export LD_LIBRARY_PATH="$vendor_root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$vendor_root/libexec/clang-real" -resource-dir "$vendor_root/resource" "$@"
EOF
chmod +x "$vendor_root/bin/clang" "$vendor_root/libexec/clang-real"

du -sh "$vendor_root"
