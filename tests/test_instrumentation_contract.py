from __future__ import annotations

import re
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTRUMENTATION = ROOT / "firmware" / "instrumentation"


class InstrumentationContractTests(unittest.TestCase):
    def test_required_event_ids_are_stable(self) -> None:
        header = (INSTRUMENTATION / "trace_events.h").read_text(encoding="utf-8")
        required = [
            "TRACE_IRQ_ASSERT",
            "TRACE_ISR_ENTRY",
            "TRACE_ISR_EXIT",
            "TRACE_SPI_STATUS_START",
            "TRACE_SPI_STATUS_END",
            "TRACE_SPI_FRAME_START",
            "TRACE_SPI_FRAME_END",
            "TRACE_SPI_CIR_START",
            "TRACE_SPI_CIR_END",
            "TRACE_UART_ENQUEUE_START",
            "TRACE_UART_ENQUEUE_END",
            "TRACE_UART_TX_START",
            "TRACE_UART_TX_END",
            "TRACE_CIR_READ_START",
            "TRACE_CIR_READ_END",
            "TRACE_PHASE_START",
            "TRACE_PHASE_END",
            "TRACE_FILTER_START",
            "TRACE_FILTER_END",
            "TRACE_FRAME_START",
            "TRACE_FRAME_END",
        ]
        for expected_id, name in enumerate(required):
            self.assertRegex(
                header,
                rf"\b{re.escape(name)}\s*=\s*{expected_id}\b",
                msg=f"{name} must retain event id {expected_id}",
            )

    def test_disabled_calls_are_non_evaluating_macros(self) -> None:
        header = (INSTRUMENTATION / "trace_gpio.h").read_text(encoding="utf-8")
        self.assertRegex(header, r"#define\s+UWB_TIMING_TRACE_ENABLE\s+0\b")
        for api in ("trace_event_set", "trace_event_clear", "trace_event_pulse"):
            self.assertRegex(
                header,
                rf"#define\s+{api}\(event_\)\s+\(\(void\)0\)",
            )

    def test_portable_backend_has_no_blocking_or_stdio_calls(self) -> None:
        source = "\n".join(
            (INSTRUMENTATION / name).read_text(encoding="utf-8")
            for name in ("trace_gpio.c", "timing_probe.c")
        )
        forbidden_calls = (
            "printf",
            "fprintf",
            "sprintf",
            "snprintf",
            "puts",
            "sleep",
            "Sleep",
            "malloc",
            "calloc",
            "realloc",
            "free",
        )
        for name in forbidden_calls:
            self.assertIsNone(re.search(rf"\b{re.escape(name)}\s*\(", source))
        for vendor_header in ("deca_device_api.h", "boards.h", "port.h", "sdk_config.h"):
            self.assertNotIn(vendor_header, source)

    def test_sources_compile_when_c_compiler_is_available(self) -> None:
        compiler = shutil.which("gcc") or shutil.which("clang") or shutil.which("cl")
        if compiler is None:
            self.skipTest("gcc/clang/cl is not on PATH; static contract tests still apply")

        disabled_main = r"""
            #include "trace_gpio.h"
            int main(void) {
                int side_effect = 0;
                trace_event_set((trace_event_t)(++side_effect));
                trace_event_clear((trace_event_t)(++side_effect));
                trace_event_pulse((trace_event_t)(++side_effect));
                return side_effect;
            }
        """
        enabled_main = r"""
            #include <stddef.h>
            #include <stdint.h>
            #include "trace_gpio.h"

            static unsigned int writes;
            static uint64_t ticks;

            static void write_pin(void *context, trace_gpio_pin_t pin, uint8_t level) {
                (void)context;
                (void)pin;
                (void)level;
                writes += 1u;
            }

            static uint64_t now_ticks(void *context) {
                (void)context;
                ticks += UINT64_C(1);
                return ticks;
            }

            int main(void) {
                static const trace_gpio_route_t routes[TRACE_EVENT_COUNT] = {
                    [TRACE_ISR_ENTRY] = { 1u, 1u, 1u },
                    [TRACE_ISR_EXIT] = { 1u, 1u, 1u },
                    [TRACE_ERROR_PULSE] = { 2u, 1u, 1u }
                };
                timing_probe_record_t records[4];
                timing_probe_t probe;
                trace_gpio_config_t config;

                timing_probe_init(&probe, records, 4u, now_ticks, NULL);
                config.routes = routes;
                config.route_count = (size_t)TRACE_EVENT_COUNT;
                config.write = write_pin;
                config.write_context = NULL;
                config.software_probe = &probe;
                config.gpio_enabled = 1u;
                config.software_timestamp_enabled = 1u;
                if (trace_gpio_configure(&config) != TRACE_GPIO_CONFIG_OK) {
                    return 10;
                }
                trace_event_set(TRACE_ISR_ENTRY);
                trace_event_clear(TRACE_ISR_EXIT);
                trace_event_pulse(TRACE_ERROR_PULSE);
                if (writes != 4u) {
                    return 11;
                }
#if UWB_TIMING_TRACE_SOFTWARE_ENABLE
                if (timing_probe_count(&probe) != 3u) {
                    return 12;
                }
                if ((records[0].action != TRACE_ACTION_SET) ||
                    (records[1].action != TRACE_ACTION_CLEAR) ||
                    (records[2].action != TRACE_ACTION_PULSE)) {
                    return 13;
                }
#else
                if (timing_probe_count(&probe) != 0u) {
                    return 14;
                }
#endif
                return 0;
            }
        """

        self._compile_and_run(
            compiler, disabled_main, enabled=False, software_enabled=False
        )
        self._compile_and_run(
            compiler, enabled_main, enabled=True, software_enabled=False
        )
        self._compile_and_run(
            compiler, enabled_main, enabled=True, software_enabled=True
        )

    def _compile_and_run(
        self,
        compiler: str,
        source: str,
        *,
        enabled: bool,
        software_enabled: bool,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            main_c = tmp_path / "main.c"
            executable = tmp_path / ("instrumentation_test.exe" if os.name == "nt" else "instrumentation_test")
            main_c.write_text(textwrap.dedent(source), encoding="utf-8")
            compiler_name = Path(compiler).name.lower()
            sources = [
                str(main_c),
                str(INSTRUMENTATION / "trace_gpio.c"),
                str(INSTRUMENTATION / "timing_probe.c"),
            ]
            if compiler_name in {"cl", "cl.exe"}:
                command = [
                    compiler,
                    "/nologo",
                    "/std:c11",
                    "/W4",
                    "/WX",
                    f"/I{INSTRUMENTATION}",
                ]
                if enabled:
                    command.extend(
                        [
                            "/DUWB_TIMING_TRACE_ENABLE=1",
                            f"/DUWB_TIMING_TRACE_SOFTWARE_ENABLE={int(software_enabled)}",
                        ]
                    )
                command.extend(sources)
                command.append(f"/Fe:{executable}")
            else:
                command = [
                    compiler,
                    "-std=c99",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    f"-I{INSTRUMENTATION}",
                ]
                if enabled:
                    command.extend(
                        [
                            "-DUWB_TIMING_TRACE_ENABLE=1",
                            f"-DUWB_TIMING_TRACE_SOFTWARE_ENABLE={int(software_enabled)}",
                        ]
                    )
                command.extend(sources)
                command.extend(["-o", str(executable)])
            # Keep compiler output as bytes: MSVC may mix its active code page
            # with UTF-8 paths, which is not reliably decodable on all hosts.
            subprocess.run(command, check=True, capture_output=True)
            subprocess.run([str(executable)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
