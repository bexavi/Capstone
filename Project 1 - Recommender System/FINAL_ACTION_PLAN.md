# FINAL ACTION PLAN - Movie Recommender Project

**Team:** B. Nkomo, Peter Mangoro, Masheia Dzimba  
**Target Grade:** 95-100/100  
**Estimated Time:** 6-8 hours total

---

## 🎯 **CRITICAL FINDING: ALL 4 ANALYTICAL QUESTIONS ARE COMPLETE!**

Your notebook contains:
- ✅ **3.1:** Taste Overlap Without Algorithms
- ✅ **3.2:** Genre Preference Profiles  
- ✅ **3.3:** Long-Tail Problem
- ✅ **3.4:** Director & Genre Co-Occurrence

**What you need to do:** Simply mark Q2 and Q3 as "submitted for grading" (as planned in your approach).

---

## 📋 **MUST-DO LIST** (Required for 100/100)

### **1. Add 3 Required Visualizations** ⚠️ **CRITICAL**

Assignment states: *"At minimum, the rating distribution, community detection clusters, and algorithm comparison results should include visual representations."*

| Visualization | Section | Code Provided | Time | Owner |
|--------------|---------|---------------|------|-------|
| Rating Distribution Histogram | 2.4 | ✅ Yes | 1 hour | B. Nkomo |
| Community Detection Network | GDS 5 | ✅ Yes | 1.5 hours | Peter |
| Algorithm Comparison Chart | GDS 4 | ✅ Yes | 1 hour | Masheia |

**All code provided in:** `PROJECT_EVALUATION_AND_COMPLETION.md`

---

### **2. Add References Section** ⚠️ **REQUIRED**

Add at the very end of the notebook:

```markdown
---

## References

### Course Materials
Leskovec, J., Rajaraman, A., & Ullman, J. D. (2020). *Mining of Massive Datasets*, Chapter 9: Recommendation Systems.

### Neo4j Documentation
- Neo4j Graph Data Science Library. https://neo4j.com/docs/graph-data-science/current/
- Node Similarity (Jaccard). https://neo4j.com/docs/graph-data-science/current/algorithms/node-similarity/
- k-Nearest Neighbors. https://neo4j.com/docs/graph-data-science/current/algorithms/knn/
- FastRP. https://neo4j.com/docs/graph-data-science/current/machine-learning/node-embeddings/fastrp/
- Louvain Community Detection. https://neo4j.com/docs/graph-data-science/current/algorithms/louvain/

### Academic Literature
Koren, Y., Bell, R., & Volinsky, C. (2009). Matrix Factorization Techniques for Recommender Systems. *IEEE Computer*, 42(8), 30-37.
Herlocker, J. L., Konstan, J. A., Terveen, L. G., & Riedl, J. T. (2004). Evaluating Collaborative Filtering Recommender Systems. *ACM Transactions on Information Systems*, 22(1), 5-53.
```

**Time:** 15 minutes  
**Owner:** B. Nkomo

---

### **3. Mark Q2 and Q3 for Grading** ⚠️ **IMPORTANT**

Add this note at the start of Section 3:

```markdown
## 3. Deeper Analytical Questions

**Note:** This notebook includes all four analytical questions for comprehensive analysis. 
**Questions 2 (Genre Preference Profiles) and 3 (Long-Tail Problem) are submitted for grading** 
as specified in our approach document. Questions 1 and 4 are included as supplementary analysis.

---

### 3.1 Taste Overlap Without Algorithms *(Supplementary Analysis)*
[existing content]

### 3.2 Genre Preference Profiles ***(Submitted for Grading - 15 points)***
[existing content]

### 3.3 Long-Tail Problem ***(Submitted for Grading - 15 points)***
[existing content]

### 3.4 Director and Genre Co-Occurrence *(Supplementary Analysis)*
[existing content]
```

**Time:** 10 minutes  
**Owner:** B. Nkomo

---

### **4. Enhanced Commentary** ⚠️ **HIGH IMPACT**

Replace basic commentary with interpretive analysis. Examples provided in `ENHANCED_COMMENTARY_EXAMPLES.md`.

**Priority Sections:**
1. EDA 2.1-2.8: Add "Implications for..." paragraphs
2. GDS 1: Explain what Jaccard captures vs misses
3. GDS 2: Explain Jaccard vs kNN divergence with examples
4. GDS 4: Add comparison table (Pure Collaborative vs Hybrid)
5. GDS 5: Acknowledge evaluation limitations explicitly

**Time:** 3-4 hours  
**Distribution:**
- B. Nkomo: EDA sections (1.5 hours)
- Peter: GDS 1-3 (1.5 hours)
- Masheia: GDS 4-5 (1 hour)

---

### **5. Figure Captions** ⚠️ **REQUIRED**

Every visualization needs a descriptive caption. Template:

```markdown
> **Figure X: [Title]**  
> [2-3 sentence description of what the figure shows and what insight it provides]
```

**Examples:**

> **Figure 1: Rating Distribution Across All User-Movie Interactions**  
> The histogram reveals moderate rating inflation, with 60% of ratings at 4-5 stars. This positive skew reduces the discriminative power of magnitude-based similarity (cosine), making binary overlap metrics (Jaccard) nearly as effective.

> **Figure 2: User Taste Communities Identified by Louvain Algorithm**  
> The network visualization shows users (nodes) connected by cosine similarity edges (kNN), colored by detected communities. The algorithm identified 3-5 distinct taste clusters based on shared genre preferences.

**Time:** 30 minutes  
**Owner:** Whoever creates the visualization

---

## ✅ **SHOULD-DO LIST** (Quality Polish)

### **6. Table Captions**

Add captions above important tables:

> **Table 1: Top 10 Most-Rated Movies**  
> Comparison of user-computed ratings vs external quality scores reveals strong agreement, validating collaborative filtering approach.

**Time:** 30 minutes  
**Owner:** All (add as you review sections)

---

### **7. Spell-Check & Grammar**

- Run spell-check on all markdown cells
- Check for:
  - Consistent capitalization (Movie titles, user names)
  - Proper punctuation
  - Complete sentences

**Time:** 1 hour  
**Owner:** Masheia (final pass)

---

### **8. Code Cell Cleanup**

Remove:
- Debug print statements
- Commented-out old code
- Unnecessary warnings (or add `warnings.filterwarnings('ignore')` if needed)

**Time:** 30 minutes  
**Owner:** Peter

---

### **9. Comparison Table for GDS 4**

Create side-by-side comparison showing Pure Collaborative vs Hybrid:

```python
# Example code in PROJECT_EVALUATION_AND_COMPLETION.md
comparison_df = pd.DataFrame({
    'Rank': [1, 2, 3, 4, 5],
    'Pure Collaborative': collab_recs['movie'].values,
    'Hybrid (70/30)': hybrid_recs['movie'].values
})
```

**Time:** 30 minutes  
**Owner:** Masheia

---

## 🎨 **NICE-TO-HAVE** (Extra Credit)

### **10. Additional Visualizations**

- Genre preference heatmap (Section 3.2)
- Long-tail distribution curve (Section 3.3)
- Cutoff sensitivity chart (Extension 1)

**Time:** 2 hours  
**Owner:** Optional - split if time permits

---

## 📅 **TIMELINE** (Recommended 2-Day Sprint)

### **Day 1: Critical Requirements** (4-5 hours)

**Hour 1-2:** Visualizations
- B. Nkomo: Rating distribution histogram
- Peter: Community detection visualization  
- Masheia: Algorithm comparison chart

**Hour 3-4:** Enhanced Commentary
- All: Add interpretive commentary to assigned sections

**Hour 5:** References & Marking
- B. Nkomo: Add references section
- B. Nkomo: Mark Q2/Q3 for grading
- All: Add figure captions

---

### **Day 2: Quality Polish** (2-3 hours)

**Hour 1:** Table captions & code cleanup
- All: Add table captions
- Peter: Clean code cells

**Hour 2:** Final review
- Masheia: Spell-check & grammar
- All: Read-through and consistency check

**Hour 3:** Submission prep
- Verify all code cells execute
- Export as: `Team_Movie_Recommender_Final.ipynb`
- Each team member uploads their copy

---

## ✅ **PRE-SUBMISSION CHECKLIST**

Print this and check off before submitting:

### **Content Completeness**
- [ ] All 8 EDA queries with results + commentary
- [ ] Q2 and Q3 marked for grading (with note explaining all 4 are included)
- [ ] All 5 GDS tasks with enhanced commentary
- [ ] All 4 extensions present

### **Required Visualizations**
- [ ] Rating distribution histogram (Section 2.4)
- [ ] Community detection visualization (GDS 5)
- [ ] Algorithm comparison chart (GDS 4 or Ext 3)

### **Professional Standards**
- [ ] References section at end
- [ ] All figures have captions
- [ ] All tables have captions
- [ ] No spelling/grammar errors
- [ ] Clean code cells (no debug artifacts)
- [ ] Consistent formatting throughout

### **Technical Correctness**
- [ ] All code cells execute without errors
- [ ] GDS projections correctly designed
- [ ] Algorithm parameters justified in commentary
- [ ] Results displayed clearly (formatted tables)

### **Commentary Quality**
- [ ] Interpretive (not just descriptive)
- [ ] Connects to MMDS Chapter 9 concepts
- [ ] Acknowledges limitations where appropriate
- [ ] Discusses production implications

### **Team Coordination**
- [ ] All team members' names on notebook
- [ ] Names consistent throughout (fix: "Masheia" vs "Marcia")
- [ ] Each person submits their own copy
- [ ] File named: `Team_Movie_Recommender_Final.ipynb`

---

## 🎯 **EXPECTED GRADE AFTER COMPLETION**

| Component | Max Points | Expected | Notes |
|-----------|-----------|----------|-------|
| EDA Queries | 20 | 19-20 | Strong queries, enhanced commentary |
| Analytical Q2 & Q3 | 30 | 28-30 | Excellent implementation |
| GDS Tasks 1-5 | 50 | 47-50 | Complete, with visualizations |
| **Total** | **100** | **94-100** | Depends on commentary quality |

**Most Likely Grade:** **96-98/100**

Potential deductions:
- -1 to -2 if commentary still too basic (unlikely if you use provided examples)
- -1 if visualizations lack captions
- -1 if references incomplete

---

## 📂 **RESOURCE FILES PROVIDED**

1. **PROJECT_EVALUATION_AND_COMPLETION.md**
   - Detailed assessment of what's complete vs missing
   - All visualization code (copy-paste ready)
   - References section template
   - Comparison table examples

2. **ENHANCED_COMMENTARY_EXAMPLES.md**
   - Before/After examples for EDA commentary
   - Before/After examples for GDS commentary
   - Commentary transformation pattern guide
   - Theory connections (MMDS Chapter 9)

3. **This File (FINAL_ACTION_PLAN.md)**
   - Task breakdown by person
   - Timeline with hour-by-hour plan
   - Pre-submission checklist
   - Expected grade breakdown

---

## 💬 **TEAM COORDINATION TIPS**

### **Communication**
- Daily stand-up (15 min): What did you do? What will you do? Any blockers?
- Share work via GitHub or Google Drive
- Review each other's commentary for consistency

### **Integration**
- One person (B. Nkomo) maintains the "master" notebook
- Others submit sections via markdown files or code snippets
- Final merge session: All together to ensure no conflicts

### **Quality Assurance**
- Cross-review: Each person reviews one other person's sections
- Final read-through: All sections, all together, out loud

---

## 🚀 **FINAL MESSAGE**

**You're 85% done!** The hard technical work is complete. What remains is:
1. Adding required visualizations (4-5 hours with provided code)
2. Enhancing commentary to be interpretive (3-4 hours with examples)
3. Professional polish (2-3 hours)

**Total remaining:** 6-8 hours across 3 people = ~2-3 hours per person

**Your FAERS score (92/100) proves you can write excellent commentary.** Apply those same skills here:
- Interpret, don't describe
- Connect to theory
- Acknowledge limitations
- Discuss business impact

**You've got this!** 🎯

---

**END OF ACTION PLAN**
