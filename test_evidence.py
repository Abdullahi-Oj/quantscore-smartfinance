"""
Test the Evidence Layer with a sample file.
"""
from evidence_layer import EvidenceExtractor

# Test with a PDF (replace with actual file path)
file_path = "path/to/your/opay_statement.pdf"

extractor = EvidenceExtractor(file_path)
result = extractor.extract()

print(f"Success: {result['success']}")
print(f"Transactions found: {result['transaction_count']}")
print(f"Confidence: {result['confidence_score']:.2%}")

if result['transactions']:
    print("\nFirst transaction:")
    print(result['transactions'][0])

if result['errors']:
    print("\nErrors:")
    for error in result['errors']:
        print(f"  - {error}")