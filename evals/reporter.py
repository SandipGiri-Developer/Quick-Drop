from dataclasses import dataclass


@dataclass
class EvalResult:
    name: str
    passed: bool
    expected: str
    observed: str
    error: str = ""

class Reporter:
    def __init__(self) -> None:
        self.results: list[EvalResult] = []

    def add_result(self, result: EvalResult) -> None:
        self.results.append(result)

    def print_report(self) -> bool:
        print("\nQuickDrop Evaluation")
        print("=====================\n")

        standard_cases = [r for r in self.results if not r.name.startswith("Adversarial")]
        adversarial_cases = [r for r in self.results if r.name.startswith("Adversarial")]

        for res in standard_cases:
            status = "PASS" if res.passed else "FAIL"
            print(f"{res.name.ljust(40)} {status}")
            if not res.passed:
                print(f"  -> Expected: {res.expected}")
                print(f"  -> Observed: {res.observed}")
                if res.error:
                    print(f"  -> Error: {res.error}")

        print("\nAdditional Safety Tests")
        print("------------------------")
        for res in adversarial_cases:
            status = "PASS" if res.passed else "FAIL"
            print(f"{res.name.ljust(40)} {status}")
            if not res.passed:
                print(f"  -> Expected: {res.expected}")
                print(f"  -> Observed: {res.observed}")
                if res.error:
                    print(f"  -> Error: {res.error}")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        score = int((passed / total) * 100) if total > 0 else 0

        print("\n--------------------------------")
        print(f"Passed:  {passed:02d}")
        print(f"Failed:  {failed:02d}")
        print(f"Score:   {score}%")
        
        overall = "PASS" if failed == 0 else "FAIL"
        print(f"\nOverall: {overall}")
        
        return failed == 0
