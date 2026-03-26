#!/bin/bash
#
# RDA Analysis with SMT2 Verification Script
#
# This script runs RDA-compliant SSA analysis on a C file and verifies
# the results against a corresponding SMT2 file.
#
# Usage:
#   ./run_rda_smt2.sh <c_file> <smt2_file> [output_file]
#   ./run_rda_smt2.sh Original/tcas_v11.c smt2_files/out.tcas_v11.smt2
#   ./run_rda_smt2.sh Original/tcas_v11.c smt2_files/out.tcas_v11.smt2 results/output.txt
#
# Or run for all files:
#   ./run_rda_smt2.sh --all

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print usage
usage() {
    echo "Usage: $0 <c_file> <smt2_file> [output_file]"
    echo "   or: $0 --all"
    echo ""
    echo "Examples:"
    echo "  $0 Original/tcas_v11.c smt2_files/out.tcas_v11.smt2"
    echo "  $0 Original/tcas_v11.c smt2_files/out.tcas_v11.smt2 results/analysis_v11_rda_smt2.txt"
    echo "  $0 --all"
    exit 1
}

# Function to run RDA with SMT2 verification for a single file
run_analysis() {
    local c_file="$1"
    local smt2_file="$2"
    local output_file="${3:-}"
    
    # Check if files exist
    if [ ! -f "$c_file" ]; then
        echo -e "${RED}Error: C file not found: $c_file${NC}" >&2
        return 1
    fi
    
    if [ ! -f "$smt2_file" ]; then
        echo -e "${YELLOW}Warning: SMT2 file not found: $smt2_file${NC}" >&2
        echo "Continuing without SMT2 verification..."
        smt2_file=""
    fi
    
    # Get project root directory (assuming script is in ssa_analyzer/)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    echo -e "${GREEN}Processing: $c_file${NC}"
    if [ -n "$smt2_file" ]; then
        echo "  SMT2 file: $smt2_file"
    fi
    
    # Run Python analysis
    python3 << PYEOF
import sys
import os
sys.path.insert(0, '.')

from ssa_analyzer.ssa_analyzer.smt2_verifier import verify_ssa_versions_for_file
from ssa_analyzer.ssa_analyzer.formatters import format_cli_output

try:
    c_file = "$c_file"
    smt2_file = "$smt2_file"
    output_file = "$output_file"
    
    # Run RDA analysis with SMT2 verification
    if smt2_file and os.path.exists(smt2_file):
        results = verify_ssa_versions_for_file(c_file, smt2_file, use_rda=True)
    else:
        # Fallback to RDA without SMT2 verification
        from ssa_analyzer.ssa_analyzer.rda_ssa_generator import get_ssa_versions_for_file_rda
        results = get_ssa_versions_for_file_rda(c_file)
    
    # Format output
    output = format_cli_output(results, 'text')
    
    # Write output
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"✓ Results written to: {output_file}")
    else:
        print(output)
        
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYEOF
    
    echo ""
}

# Function to run analysis for all files
run_all() {
    local project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    cd "$project_root"
    
    echo -e "${GREEN}Running RDA + SMT2 verification for all files...${NC}"
    echo ""
    
    local count=0
    local success=0
    local failed=0
    
    for c_file in Original/tcas_v*.c; do
        if [ ! -f "$c_file" ]; then
            continue
        fi
        
        base=$(basename "$c_file" .c)
        smt2_file="smt2_files/out.${base}.smt2"
        output_file="ssa_analyzer/results/analysis_${base}_rda_smt2.txt"
        
        count=$((count + 1))
        
        if run_analysis "$c_file" "$smt2_file" "$output_file"; then
            success=$((success + 1))
        else
            failed=$((failed + 1))
        fi
    done
    
    echo ""
    echo -e "${GREEN}=== Summary ===${NC}"
    echo "Total files: $count"
    echo -e "${GREEN}Successful: $success${NC}"
    if [ $failed -gt 0 ]; then
        echo -e "${RED}Failed: $failed${NC}"
    fi
}

# Main script logic
if [ $# -eq 0 ]; then
    usage
elif [ "$1" = "--all" ] || [ "$1" = "-a" ]; then
    run_all
elif [ $# -lt 2 ]; then
    echo -e "${RED}Error: Missing required arguments${NC}" >&2
    usage
else
    run_analysis "$1" "$2" "${3:-}"
fi

