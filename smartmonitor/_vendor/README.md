# Vendored code

`library/` is taken from
[turing-smart-screen-python-HIDdev2](https://github.com/Agentry433/turing-smart-screen-python-HIDdev2)
(itself a fork of [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python)),
licensed **GPL-3.0**. `LICENSE`, `COPYRIGHT` and `AUTHORS` are its originals.

Only the theme-compilation path is used: `smartmonitor_ui` (the RC4 `.ui` codec)
and `smartmonitor_compile` with its dependencies `smartmonitor_imgdat`,
`smartmonitor_render` and `log`.

It lives inside the package rather than beside it so imports resolve when this
project is pip-installed, not only when run from a clone. The modules import
each other as `library.x`, so `smartmonitor/_vendor` is placed on `sys.path`
instead of rewriting them — keeping the vendored files byte-identical upstream.
