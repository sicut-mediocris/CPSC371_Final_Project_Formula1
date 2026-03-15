import PyPDF2
import sys

def main():
    try:
        reader = PyPDF2.PdfReader('CPSC 371_ Project Proposal.pdf')
        text = ''
        for page in reader.pages:
            text += page.extract_text() + '\n'
        with open('output.txt', 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
