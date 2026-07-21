from evidence_layer.parsers.moniepoint_pdf_parser import MoniepointPDFParser

parser = MoniepointPDFParser("moniepoint_sample.pdf")

result = parser.extract()

print(result)