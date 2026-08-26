import argparse
import csv
from pathlib import Path

from config.settings import DEFAULT_ENCODING


def create_small_sample(
    input_path: str,
    output_path: str,
    rows: int,
) -> None:
    """
    Create a reproducible small CSV sample using streaming.

    The full source file is never loaded into memory.
    """

    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_file}"
        )

    if not input_file.is_file():
        raise ValueError(
            f"Input path is not a file: {input_file}"
        )

    if rows <= 0:
        raise ValueError(
            "--rows must be greater than zero."
        )

    # Create output directory if needed
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows_written = 0

    print("\n========== CREATE SMALL SAMPLE ==========")
    print(f"Input file : {input_file}")
    print(f"Output file: {output_file}")
    print(f"Requested rows: {rows}")

    with input_file.open(
        mode="r",
        encoding=DEFAULT_ENCODING,
        newline="",
    ) as source_file:

        reader = csv.reader(source_file)

        with output_file.open(
            mode="w",
            encoding=DEFAULT_ENCODING,
            newline="",
        ) as target_file:

            writer = csv.writer(target_file)

            # Copy header
            try:
                header = next(reader)
            except StopIteration:
                raise ValueError(
                    "Input CSV file is empty."
                )

            writer.writerow(header)

            # Stream rows one by one
            for row in reader:

                writer.writerow(row)

                rows_written += 1

                if rows_written >= rows:
                    break

    print(f"Rows written: {rows_written}")
    print("Sample created successfully.")
    print("========================================\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a small reproducible CSV sample "
            "using streaming."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the source CSV file.",
    )

    parser.add_argument(
        "--output",
        default="data/orders_small_sample.csv",
        help=(
            "Path for the generated sample. "
            "Default: data/orders_small_sample.csv"
        ),
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=100000,
        help=(
            "Number of data rows to copy. "
            "Default: 100000"
        ),
    )

    args = parser.parse_args()

    create_small_sample(
        input_path=args.input,
        output_path=args.output,
        rows=args.rows,
    )


if __name__ == "__main__":
    main()