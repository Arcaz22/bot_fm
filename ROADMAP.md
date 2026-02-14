# Finance Bot - Feature Roadmap

## ✅ Sudah Implemented (V1.0)
- [x] Natural language transaction parsing
- [x] Income/Expense/Transfer tracking
- [x] Multi-wallet support
- [x] Category management
- [x] Balance summary
- [x] Transaction history
- [x] OCR receipt scanning (Gemini Vision)
- [x] Split receipt by items
- [x] Hybrid intent detection (keyword + LLM)

---

## 🚀 Phase 2: Core Enhancement (Recommended Next)

### 1. **Recurring Transactions** ⭐⭐⭐
**Use Case:** Netflix 199rb/bulan, Spotify 54rb/bulan, gaji bulanan

**Implementation:**
```python
class MstRecurringTemplate(Base):
    user_id: int
    name: str  # "Netflix Subscription"
    amount: float
    category_id: int
    wallet_id: int
    frequency: str  # 'daily', 'weekly', 'monthly', 'yearly'
    start_date: date
    end_date: Optional[date]
    is_active: bool
    last_generated: Optional[datetime]
```

**Features:**
- Auto-create transaction setiap periode
- Reminder sebelum jatuh tempo
- Skip/pause untuk bulan tertentu
- Report: "Recurring expenses 2M this month"

**Command:**
```
User: "Netflix 199rb per bulan dari BCA"
Bot: ✅ Recurring expense created! Auto-record setiap tanggal 20
```

---

### 2. **Budget Limits & Alerts** ⭐⭐⭐
**Use Case:** Budget makanan 1jt/bulan, transport 500rb/bulan

**Implementation:**
```python
class MstBudget(Base):
    user_id: int
    category_id: int
    period: str  # 'daily', 'weekly', 'monthly'
    limit_amount: float
    alert_threshold: float = 0.8  # 80% alert
    start_date: date
```

**Features:**
- Real-time spending vs budget
- Alert saat 80% dan 100% terlewati
- Visualization: Progress bar
- Rollover unused budget (optional)

**Command:**
```
User: "set budget makanan 1jt per bulan"
Bot: ✅ Budget set!
     Current spending: 450k (45%)
     Remaining: 550k (16 days left)
```

---

### 3. **Smart Analytics & Insights** ⭐⭐⭐
**Use Case:** "Spending di kafe naik 30% bulan ini", "Top 3 category pengeluaran"

**Implementation:**
```python
# Service layer
class AnalyticsService:
    async def get_spending_trends(user_id, period='month'):
        # Compare with previous period
        # Return: {"Food": {"current": 2M, "prev": 1.5M, "change": +33%}}

    async def get_category_breakdown(user_id, period='month'):
        # Pie chart data

    async def predict_month_end(user_id):
        # Linear regression based on daily spending
```

**Reports:**
- Monthly summary (PDF/Image)
- Spending by category (pie chart)
- Daily average tracking
- Anomaly detection: "Unusual spending today: 500k (avg: 150k)"

---

### 4. **Savings Goals** ⭐⭐
**Use Case:** Nabung untuk iPhone 20jt, liburan 10jt

**Implementation:**
```python
class TrsSavingsGoal(Base):
    user_id: int
    name: str  # "iPhone 15 Pro"
    target_amount: float
    current_amount: float = 0
    deadline: Optional[date]
    status: str  # 'active', 'completed', 'cancelled'
```

**Features:**
- Progress tracking
- Auto-suggest: "Save 500k/month to reach goal"
- Celebrate milestones: 25%, 50%, 75%, 100%
- Link to specific wallet (e.g., "Savings Account")

**Command:**
```
User: "target nabung iPhone 20jt"
Bot: 🎯 Goal created!
     Progress: 0/20,000,000
     Suggestion: Save 1.67M/month for 12 months
```

---

### 5. **Export & Reporting** ⭐⭐
**Use Case:** Share laporan ke akuntan, backup data

**Features:**
- Export to Excel (.xlsx)
- Export to CSV
- Generate PDF report with charts
- Email/Telegram document delivery

**Format:**
```
Monthly Report - January 2026
================================
Income:        5,000,000
Expenses:     -3,200,000
Net:          +1,800,000

Top Categories:
1. Food         1,200,000
2. Transport      800,000
3. Shopping       600,000

[Chart images embedded]
```

---

## 🎨 Phase 3: Advanced Features

### 6. **Multi-Currency Support** ⭐
**Use Case:** Travel abroad, invest in USD

```python
class MstCurrency(Base):
    code: str  # USD, SGD, JPY
    rate_to_idr: float

# In wallet
wallet.currency = "USD"
# Auto-convert saat calculate balance
```

---

### 7. **Collaborative Budgets** ⭐⭐
**Use Case:** Budget keluarga, patungan rumah kos

**Features:**
- Invite users ke shared budget
- Each user tracks their own expenses
- Aggregate view
- Split bills automatically

---

### 8. **Smart Categories with ML** ⭐
**Use Case:** Auto-categorize "Starbucks" → Coffee Shop → Food

```python
# Use embedding_data di transaction
# Train simple classifier
# Or use LLM few-shot learning
```

---

### 9. **Investment Tracking** ⭐
**Use Case:** Track saham, crypto, reksadana

```python
class TrsInvestment(Base):
    asset_name: str  # "BBRI", "Bitcoin"
    quantity: float
    buy_price: float
    current_price: float  # Update via API
    profit_loss: float
```

**Features:**
- Real-time portfolio value
- P&L tracking
- Link to yahoo finance API

---

### 10. **Bill Reminders** ⭐⭐
**Use Case:** Bayar listrik tanggal 20, BPJS tanggal 10

```python
class TrsReminder(Base):
    name: str
    due_date: date
    amount: Optional[float]
    status: str  # 'pending', 'paid'
    notify_days_before: int = 3
```

**Notification:**
```
🔔 Reminder: Bayar listrik dalam 3 hari
   Estimasi: 500,000
   [Mark as Paid] [Snooze]
```

---

## 🛡️ Phase 4: Enterprise/Advanced

### 11. **Data Backup & Sync**
- Auto backup to cloud
- Import from other apps (Mint, YNAB)
- API for third-party integration

### 12. **Audit Log**
- Track all changes
- Undo transactions
- Version history

### 13. **Family Accounts**
- Parent-child hierarchy
- Allowance management
- Spending limits per child

### 14. **Tax Preparation**
- Auto-categorize tax-deductible expenses
- Generate tax report
- Integration with e-Filing

---

## 💡 Quick Wins (Low effort, High impact)

### A. **Transaction Notes Enhancement**
Currently: `description` only
Add: `notes` field untuk context panjang

### B. **Search Transactions**
```
User: "cari transaksi kopi bulan lalu"
Bot: [List of coffee purchases in Dec]
```

### C. **Duplicate Detection**
Alert: "Detected similar transaction 5 mins ago, is this duplicate?"

### D. **Voice Input** (Telegram voice message)
User: [🎤 "beli kopi 25 ribu"]
Bot: OCR → Parse → Save

### E. **Quick Stats Command**
```
/stats
📊 This Month:
   • Income: 5M
   • Expense: 3.2M
   • Saving Rate: 36%
   • Top Spend: Food (1.2M)
```

---

## 🎯 Priority Matrix

| Feature | Impact | Effort | Priority | Status |
|---------|--------|--------|----------|--------|
| Recurring Transactions | High | Medium | P0 | 🟡 Planned |
| Budget Limits | High | Medium | P0 | 🟡 Planned |
| Analytics & Insights | High | High | P1 | 🟡 Planned |
| Savings Goals | Medium | Low | P1 | 🟡 Planned |
| Export to Excel | Medium | Low | P2 | ⚪ Backlog |
| Hutang-Piutang | Medium | Medium | P1 | 🟢 Model Ready |
| Search Transactions | Low | Low | P3 | ⚪ Backlog |
| Multi-Currency | Low | High | P3 | ⚪ Backlog |
| Investment Tracking | Low | High | P4 | ⚪ Backlog |

---

## 📝 Notes

**For MVP Focus:**
1. Recurring Transactions
2. Budget Limits
3. Basic Analytics

**For Viral Features:**
1. Receipt OCR (Already done! ✅)
2. Natural Language (Already done! ✅)
3. Collaborative budgets
4. Savings goals with gamification

**Technical Debt:**
- Add `notes` field to transactions
- Implement pgvector for semantic search
- Add rate limiting
- Implement caching (Redis)
