# Makefile for CTK Technical Report

MAIN = ctk_technical_report
TEX = $(MAIN).tex
PDF = $(MAIN).pdf

# LaTeX compiler
LATEX = pdflatex
BIBTEX = bibtex

# Build options
LATEX_FLAGS = -interaction=nonstopmode -halt-on-error

.PHONY: all clean distclean view

# Default target
all: $(PDF)

# Build PDF (run twice for references)
$(PDF): $(TEX)
	$(LATEX) $(LATEX_FLAGS) $(TEX)
	$(LATEX) $(LATEX_FLAGS) $(TEX)

# Build with bibliography
bib: $(TEX)
	$(LATEX) $(LATEX_FLAGS) $(TEX)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(LATEX_FLAGS) $(TEX)
	$(LATEX) $(LATEX_FLAGS) $(TEX)

# Quick build (single pass)
quick: $(TEX)
	$(LATEX) $(LATEX_FLAGS) $(TEX)

# View PDF
view: $(PDF)
	xdg-open $(PDF) 2>/dev/null || open $(PDF) 2>/dev/null || echo "Please open $(PDF) manually"

# Clean auxiliary files
clean:
	rm -f *.aux *.log *.out *.toc *.bbl *.blg *.synctex.gz

# Clean everything including PDF
distclean: clean
	rm -f $(PDF)

# Help
help:
	@echo "CTK Technical Report Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all (default) - Build PDF with two passes"
	@echo "  bib          - Build with bibliography"
	@echo "  quick        - Single pass build"
	@echo "  view         - Open PDF in viewer"
	@echo "  clean        - Remove auxiliary files"
	@echo "  distclean    - Remove all generated files"
	@echo "  help         - Show this help message"
