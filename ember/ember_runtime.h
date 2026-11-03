/* The Ember runtime: pasted at the top of every generated C file.
 *
 * Every runtime error goes through ember_panic, which names the line of the .em file.
 * Every allocation goes through ember_alloc. Version 1 never frees; ownership plugs in here later.
 */
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char *ptr;
    int64_t len;
} ember_str;

static const char *ember_file = "?";

static void ember_panic(int line, const char *message) {
    fflush(stdout);
    fprintf(stderr, "error: %s\n --> %s:%d\n", message, ember_file, line);
    exit(1);
}

static void *ember_alloc(size_t size) {
    void *memory = malloc(size ? size : 1);
    if (!memory) {
        fprintf(stderr, "error: out of memory\n");
        exit(1);
    }
    return memory;
}

/* ---- whole numbers: overflow is an error, never a silent wrap-around ---- */

static inline int64_t ember_add(int64_t a, int64_t b, int line) {
    int64_t result;
    if (__builtin_add_overflow(a, b, &result)) ember_panic(line, "this addition is too big for an int");
    return result;
}

static inline int64_t ember_sub(int64_t a, int64_t b, int line) {
    int64_t result;
    if (__builtin_sub_overflow(a, b, &result)) ember_panic(line, "this subtraction is too big for an int");
    return result;
}

static inline int64_t ember_mul(int64_t a, int64_t b, int line) {
    int64_t result;
    if (__builtin_mul_overflow(a, b, &result)) ember_panic(line, "this multiplication is too big for an int");
    return result;
}

static inline int64_t ember_neg(int64_t a, int line) {
    if (a == INT64_MIN) ember_panic(line, "negating this is too big for an int");
    return -a;
}

/* Like Python, the remainder takes the sign of the divisor: -7 % 3 is 2. */
static inline int64_t ember_mod(int64_t a, int64_t b, int line) {
    if (b == 0) ember_panic(line, "can't take the remainder of a division by zero");
    if (b == -1) return 0;
    int64_t result = a % b;
    if (result != 0 && ((result < 0) != (b < 0))) result += b;
    return result;
}

/* ---- decimals ---- */

static inline double ember_div(double a, double b, int line) {
    if (b == 0.0) ember_panic(line, "division by zero");
    return a / b;
}

static inline double ember_fmod(double a, double b, int line) {
    if (b == 0.0) ember_panic(line, "can't take the remainder of a division by zero");
    double result = fmod(a, b);
    if (result != 0.0 && ((result < 0) != (b < 0))) result += b;
    return result;
}

/* ---- text ---- */

static inline ember_str ember_str_lit(const char *ptr, int64_t len) {
    ember_str s = {ptr, len};
    return s;
}

static ember_str ember_concat(ember_str a, ember_str b) {
    char *joined = ember_alloc((size_t)(a.len + b.len));
    memcpy(joined, a.ptr, (size_t)a.len);
    memcpy(joined + a.len, b.ptr, (size_t)b.len);
    return ember_str_lit(joined, a.len + b.len);
}

static int ember_str_cmp(ember_str a, ember_str b) {
    int64_t shorter = a.len < b.len ? a.len : b.len;
    int order = memcmp(a.ptr, b.ptr, (size_t)shorter);
    if (order != 0) return order;
    return (a.len > b.len) - (a.len < b.len);
}

static inline bool ember_str_eq(ember_str a, ember_str b) {
    return a.len == b.len && memcmp(a.ptr, b.ptr, (size_t)a.len) == 0;
}

/* Text never changes, so one character is just a view into the original: no copy needed. */
static ember_str ember_str_at(ember_str s, int64_t i, int line) {
    if (i < 0 || i >= s.len) {
        char message[160];
        snprintf(message, sizeof message, "position %" PRId64 " is outside this text, which has %" PRId64
                 " character%s", i, s.len, s.len == 1 ? "" : "s");
        ember_panic(line, message);
    }
    return ember_str_lit(s.ptr + i, 1);
}

/* ---- built-in functions ---- */

static void ember_print_int(int64_t value) { printf("%" PRId64 "\n", value); }

/* Up to 15 significant digits with no trailing .0, so 14.0 prints as 14 and 0.1 + 0.2 as 0.3. */
static void ember_print_float(double value) { printf("%.15g\n", value); }

static void ember_print_bool(bool value) { puts(value ? "true" : "false"); }

static void ember_print_str(ember_str value) {
    fwrite(value.ptr, 1, (size_t)value.len, stdout);
    putchar('\n');
}

/* One line from the keyboard, without the line ending. At the end of input it gives "".
 * A UTF-8 byte-order mark at the very start of input is dropped (Windows PowerShell adds one
 * when piping text into a program). */
static bool ember_read_any_line = false;

static ember_str ember_read_line(void) {
    fflush(stdout);
    size_t capacity = 64, len = 0;
    char *buffer = ember_alloc(capacity);
    int c;
    while ((c = getchar()) != EOF && c != '\n') {
        if (len == capacity) {
            char *bigger = ember_alloc(capacity * 2);
            memcpy(bigger, buffer, len);
            buffer = bigger;
            capacity *= 2;
        }
        buffer[len++] = (char)c;
    }
    if (len > 0 && buffer[len - 1] == '\r') len--;
    if (!ember_read_any_line && len >= 3 && memcmp(buffer, "\xEF\xBB\xBF", 3) == 0) {
        buffer += 3;
        len -= 3;
    }
    ember_read_any_line = true;
    return ember_str_lit(buffer, (int64_t)len);
}

static double ember_to_float(ember_str s, int line) {
    char *text = ember_alloc((size_t)s.len + 1);
    memcpy(text, s.ptr, (size_t)s.len);
    text[s.len] = '\0';
    char *end;
    double value = strtod(text, &end);
    while (*end == ' ' || *end == '\t') end++;
    if (s.len == 0 || end == text || *end != '\0') {
        char message[200];
        snprintf(message, sizeof message, "can't turn \"%.100s\" into a number", text);
        ember_panic(line, message);
    }
    return value;
}

static inline int64_t ember_len(ember_str s) { return s.len; }
