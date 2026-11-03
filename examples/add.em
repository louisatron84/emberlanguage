# adds up numbers until we pass 10
fn add(a: int, b: int) -> int:
    return a + b

fn main():
    let step = 3
    mut total = 0
    while total < 10:
        total = add(total, step)
    print(total)
