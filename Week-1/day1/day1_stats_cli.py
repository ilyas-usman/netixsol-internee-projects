def calculate_mean(numbers):
    total = 0
    for num in numbers:
        total += num

    return total / len(numbers)

def calculate_median(numbers):
    sorted_numbers = sorted(numbers)
    n = len(sorted_numbers)

    if n % 2 == 1:
        return sorted_numbers[n // 2]
    else:
        middle1 = sorted_numbers[n // 2 - 1]
        middle2 = sorted_numbers[n // 2]
        return (middle1 + middle2) / 2

def calculate_mode(numbers):
    frequency = {}

    for num in numbers:
        if num in frequency:
            frequency[num] += 1
        else:
            frequency[num] = 1

    max_count = 0

    for count in frequency.values():
        if count > max_count:
            max_count = count

    modes = []

    for key, value in frequency.items():
        if value == max_count:
            modes.append(key)

    if max_count == 1:
        return "No Mode"

    return modes

def calculate_min(numbers):
    minimum = numbers[0]

    for num in numbers:
        if num < minimum:
            minimum = num

    return minimum

def calculate_max(numbers):
    maximum = numbers[0]

    for num in numbers:
        if num > maximum:
            maximum = num

    return maximum


def main():

    user_input = input("Enter numbers separated by spaces: ")

    numbers = []

    for value in user_input.split():
        numbers.append(float(value))

    print("\n------ Results ------")
    print("Numbers :", numbers)
    print("Mean    :", calculate_mean(numbers))
    print("Median  :", calculate_median(numbers))
    print("Mode    :", calculate_mode(numbers))
    print("Minimum :", calculate_min(numbers))
    print("Maximum :", calculate_max(numbers))


main()