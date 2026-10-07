import argparse
import sys

from evals.adversarial import AdversarialRunner
from evals.client import APIClient, PaySwiftClientAPI
from evals.loader import load_cases
from evals.reporter import Reporter
from evals.runner import Evaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QuickDrop Evaluations")
    parser.add_argument("service_url", type=str, help="The base URL of the QuickDrop service")
    parser.add_argument("--payswift-url", type=str, default="http://localhost:8081", help="The base URL of the PaySwift Sandbox")
    args = parser.parse_args()

    api_client = APIClient(args.service_url)
    payswift_client = PaySwiftClientAPI(args.payswift_url)

    # Check health
    try:
        api_client.get_health()
    except Exception as e:  # noqa: BLE001
        print(f"Error: Could not connect to QuickDrop service at {args.service_url}")
        print(e)
        sys.exit(1)

    evaluator = Evaluator(api_client, payswift_client)
    adversarial = AdversarialRunner(api_client, payswift_client)
    reporter = Reporter()

    try:
        cases = load_cases()
    except Exception as e:  # noqa: BLE001
        print(f"Error loading cases: {e}")
        sys.exit(1)

    print(f"Running {len(cases)} test cases...")
    for i, case in enumerate(cases):
        result = evaluator.run_case(i, case)
        reporter.add_result(result)

    print("Running adversarial cases...")
    reporter.add_result(adversarial.test_duplicate_message())

    success = reporter.print_report()
    
    if not success:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
