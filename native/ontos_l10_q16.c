/* Deterministic Q16.16 arithmetic oracle. Compiles with native GCC and clang wasm32.
 * This executes the arithmetic independently of the Python reference and
 * mirrors RTL source ontos_q16_core_v67.sv. It is NOT a bitstream simulator.
 */
#include <stdint.h>

static int64_t arithmetic_floor_shift16(int64_t value) {
    if (value >= 0) return value >> 16;
    return -(((-value) + 65535LL) >> 16);
}

int32_t ontos_q16_blend(int32_t mu_in, int32_t drive_in, int32_t decay_q16) {
    /* Intentional two's-complement semantics: 32-bit wrap of 1.0-decay. */
    uint32_t diff = UINT32_C(65536) - (uint32_t)decay_q16;
    int32_t one_minus_d = (int32_t)diff;
    int64_t a = (int64_t)decay_q16 * (int64_t)drive_in;
    int64_t b = (int64_t)one_minus_d * (int64_t)mu_in;
    int64_t combined = arithmetic_floor_shift16(a) + arithmetic_floor_shift16(b);
    /* The RTL output truncates the high bits on 32-bit assignment. */
    return (int32_t)(uint32_t)combined;
}
