# 📊 CLO Cashflow Modeling Engine

A Python-based cashflow modeling engine for **Collateralized Loan Obligations (CLOs)**. The engine is designed to simulate tranche-level cashflows, evaluate coverage tests, and analyze the impact of defaults and prepayments based on deal-level inputs.

---

## 🚀 Overview

This project implements a CLO cashflow engine that:

* Reads deal inputs from a structured **Excel file**
* Runs period-by-period cashflow waterfalls
* Tracks **interest payments, principal distributions, and coverage test performance**
* Allows scenario analysis by modifying **default rates** and **prepayment rates**
* Produces outputs in both **JSON** and **Excel** formats

The engine is currently based on a **sample presale report**, making it suitable for understanding and analyzing standard CLO structures.

---

## 📥 Input Requirements

To run the cashflow engine, you must provide an Excel file containing the following sheets:

1. **Tranche Information**

   * Tranche name
   * Initial balance
   * Coupon / spread
   * Tranche type
   * Seniority / rank

2. **Interest Waterfall**

   * Priority of interest payments across tranches and fees

3. **Principal Waterfall**

   * Priority of principal distributions

4. **Coverage Tests**

   * OC / IC test definitions
   * Trigger thresholds
   * Tranches affected by test failures

The engine reads these sheets, validates the structure, and uses them to construct the deal cashflow logic.

---

## ⚙️ Model Features

* Adjustable **default rate** and **prepayment rate** for scenario analysis
* Dynamic tracking of:

  * Coverage test breaches
  * Interest deferrals
  * Principal redirection during test failures
* Clear distinction between **rated tranches** and **subordinate tranches**
* Period-by-period cashflow simulation

You can easily observe:

* When coverage tests start failing
* Which tranches stop receiving interest or principal
* Whether all rated and subordinated classes are fully paid down

---

## 🧱 Supported Tranche Types (Current)

Based on the presale structure, the engine currently supports:

* **Current Pay Tranches**
* **Deferred Interest Tranches**
* **Accrued Interest Tranches**
* **Fee Tranches** (e.g., senior management fees)

---

## 📤 Outputs

The engine generates:

1. **JSON Output**

   * Complete cashflow history
   * Tranche-level interest and principal payments
   * Deferred and accrued interest tracking
   * Coverage test results by period

2. **Excel Output**

   * Tabular representation of the same outputs for easier analysis
   * Useful for validation, reporting, and sensitivity analysis

---

## 🔧 Extensibility

While the current implementation is tailored to a specific presale-style CLO, the engine is designed to be **extensible**. Additional tranche types and structural features can be incorporated, such as:

* PIK interest tranches
* Equity tranches with excess spread logic
* Multiple reinvestment and replenishment periods
* Deal-specific waterfalls and triggers

This makes the framework a strong foundation for building a **more generalized CLO cashflow engine** capable of handling a wide range of deal structures.

---

## 🧪 Use Cases

* CLO cashflow analysis
* Coverage test stress testing
* Default and prepayment sensitivity analysis
* Structured credit research and learning

---

## 📌 Disclaimer

This project is for **educational and analytical purposes only** and is based on sample presale assumptions. It should not be used for investment decisions.

---

## 🤝 Contributions

Contributions, suggestions, and extensions are welcome. Feel free to open an issue or submit a pull request.
