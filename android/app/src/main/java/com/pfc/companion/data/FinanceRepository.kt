package com.pfc.companion.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.Calendar

/** Read/write access to the shared finance API, plus session lifecycle. */
class FinanceRepository(
    private val api: ApiClient,
    private val session: SessionState,
) {
    val tokenFlow: Flow<String?> = session.tokenFlow
    val baseUrlFlow: Flow<String> = session.baseUrlFlow
    val themeFlow: Flow<String> = session.themeFlow
    val savedServers: Flow<List<String>> = session.savedServers

    suspend fun token(): String? = session.token()

    suspend fun login(email: String, password: String) {
        val response = api.post(
            "auth/login",
            LoginRequest(email.trim(), password),
            LoginRequest.serializer(),
            TokenResponse.serializer(),
        )
        session.saveToken(response.accessToken)
    }

    suspend fun register(email: String, password: String, displayName: String, timezone: String) {
        val response = api.post(
            "auth/register",
            RegisterRequest(email.trim(), password, displayName.trim(), timezone),
            RegisterRequest.serializer(),
            TokenResponse.serializer(),
        )
        session.saveToken(response.accessToken)
    }

    suspend fun logout() {
        // Best effort: the local token is cleared even when the server is unreachable.
        try {
            api.postNoContent("auth/logout")
        } catch (_: Exception) {
        }
        session.clearToken()
    }

    /**
     * Changes the password and keeps this device signed in.
     *
     * The server ends every other session and hands back a token for this one, so
     * the new token replaces the old instead of signing the user out here.
     */
    suspend fun changePassword(currentPassword: String, newPassword: String) {
        val response = try {
            api.post(
                "auth/password",
                ChangePasswordRequest(currentPassword, newPassword),
                ChangePasswordRequest.serializer(),
                TokenResponse.serializer(),
            )
        } catch (err: ApiException) {
            // Every other request treats 401 as an expired session, which is right
            // everywhere except here: the session is fine, the current password is
            // not. Say what the user can act on.
            if (err.status == 401) {
                throw ApiException(401, "Current password is incorrect.")
            }
            throw err
        }
        session.saveToken(response.accessToken)
    }

    suspend fun profile(): Profile = api.get("auth/me", Profile.serializer())

    /** Portrait changes made after setup: display name and the timezone "today" follows. */
    suspend fun updateProfile(displayName: String, timezone: String): Profile =
        api.patch(
            "auth/profile",
            buildJsonObject {
                put("display_name", displayName.trim())
                put("timezone", timezone)
            },
            Profile.serializer(),
        )

    /** Safe-to-Spend rules. The server recomputes; the body only states the inputs. */
    suspend fun updatePreferences(body: JsonObject): Preferences =
        api.patch("auth/preferences", body, Preferences.serializer())

    suspend fun updateNotifications(body: JsonObject): NotificationPreferences =
        api.patch(
            "auth/notification-preferences",
            body,
            NotificationPreferences.serializer(),
        )

    suspend fun completeOnboarding(
        displayName: String,
        timezone: String,
        accountName: String,
        startingBalance: String,
        buffer: String,
        incomeAmount: String?,
        incomeFrequency: String?,
        nextPayday: String?,
    ): Profile = api.post(
        "auth/onboarding",
        OnboardingRequest(
            displayName = displayName.trim(),
            timezone = timezone,
            incomeAmount = incomeAmount?.takeIf { it.isNotBlank() },
            incomeFrequency = incomeFrequency?.takeIf { incomeAmount?.isNotBlank() == true },
            nextPayday = nextPayday?.takeIf { it.isNotBlank() },
            startingBalance = startingBalance.ifBlank { "0.00" },
            minimumBalanceBuffer = buffer.ifBlank { "0.00" },
            accounts = listOf(
                OnboardingAccount(
                    name = accountName.trim().ifBlank { "Everyday Checking" },
                    openingBalance = startingBalance.ifBlank { "0.00" },
                )
            ),
        ),
        OnboardingRequest.serializer(),
        Profile.serializer(),
    )

    suspend fun incomeSources(): List<IncomeSource> = api.get(
        "income-sources",
        kotlinx.serialization.builtins.ListSerializer(IncomeSource.serializer()),
    )

    suspend fun createIncome(draft: IncomeDraft): IncomeSource = api.post(
        "income-sources",
        draft.toJson(editing = false),
        JsonObject.serializer(),
        IncomeSource.serializer(),
    )

    suspend fun updateIncome(id: String, draft: IncomeDraft): IncomeSource =
        api.patch("income-sources/$id", draft.toJson(editing = true), IncomeSource.serializer())

    suspend fun deleteIncome(id: String) {
        api.delete("income-sources/$id")
    }

    suspend fun dashboard(): Dashboard = api.get("dashboard", Dashboard.serializer())

    suspend fun accounts(): AccountsResponse = api.get(
        "accounts",
        AccountsResponse.serializer(),
        mapOf("include_archived" to "false"),
    )

    suspend fun categories(): List<Category> = api.get(
        "categories",
        kotlinx.serialization.builtins.ListSerializer(Category.serializer()),
        mapOf("include_archived" to "false"),
    )

    suspend fun transactions(
        limit: Int = 50,
        type: String? = null,
        search: String? = null,
    ): TransactionPage {
        val query = buildMap {
            put("sort", "-txn_date")
            put("limit", limit.toString())
            put("offset", "0")
            if (!type.isNullOrBlank()) put("tx_type", type)
            if (!search.isNullOrBlank()) put("search", search)
        }
        return api.get("transactions", TransactionPage.serializer(), query)
    }

    suspend fun createTransaction(draft: TransactionDraft): TransactionCreateResponse = api.post(
        "transactions",
        draft.toCreateBody(),
        TransactionWrite.serializer(),
        TransactionCreateResponse.serializer(),
    )

    suspend fun updateTransaction(transactionId: String, draft: TransactionDraft): Transaction = api.patch(
        "transactions/$transactionId",
        draft.toPatchJson(),
        Transaction.serializer(),
    )

    suspend fun transaction(transactionId: String): Transaction =
        api.get("transactions/$transactionId", Transaction.serializer())

    suspend fun deleteTransaction(transactionId: String) {
        api.delete("transactions/$transactionId")
    }

    suspend fun matchSuggestions(): List<MatchSuggestionGroup> =
        api.get("match-suggestions", MatchSuggestionsResponse.serializer()).items

    suspend fun confirmMatch(matchId: String, amount: String? = null) {
        if (amount.isNullOrBlank()) {
            api.postNoContent("matches/$matchId/confirm")
        } else {
            api.postNoContent("matches/$matchId/confirm", """{"amount":"$amount"}""")
        }
    }

    suspend fun rejectMatch(matchId: String) {
        api.postNoContent("matches/$matchId/reject")
    }

    suspend fun uploadCsv(
        upload: CsvUpload,
        accountId: String,
        onProgress: (Float) -> Unit = {},
    ): CsvUploadResponse = api.uploadCsv(
        path = "imports",
        upload = upload,
        fields = mapOf("account_id" to accountId),
        serializer = CsvUploadResponse.serializer(),
        onProgress = onProgress,
    )

    suspend fun previewImport(importId: String, mapping: Map<String, String?>): ImportPreview =
        api.post(
            "imports/$importId/preview",
            ImportMappingBody(mapping),
            ImportMappingBody.serializer(),
            ImportPreview.serializer(),
        )

    suspend fun commitImport(importId: String, mapping: Map<String, String?>): ImportCommitResult =
        api.post(
            "imports/$importId/commit",
            ImportMappingBody(mapping),
            ImportMappingBody.serializer(),
            ImportCommitResult.serializer(),
        )

    suspend fun importRecords(importId: String): List<ImportRecord> = api.get(
        "imports/$importId/records",
        kotlinx.serialization.builtins.ListSerializer(ImportRecord.serializer()),
    )

    suspend fun bills(): BillsResponse = api.get("bills", BillsResponse.serializer())

    suspend fun bill(id: String): Bill = api.get("bills/$id", Bill.serializer())

    suspend fun createBill(draft: BillDraft): Bill = api.post(
        "bills",
        draft.toJson(editing = false),
        JsonObject.serializer(),
        Bill.serializer(),
    )

    suspend fun updateBill(id: String, draft: BillDraft): Bill =
        api.patch("bills/$id", draft.toJson(editing = true), Bill.serializer())

    suspend fun deleteBill(id: String) {
        api.delete("bills/$id")
    }

    suspend fun upcomingOccurrences(days: Int = 60): List<Occurrence> {
        val end = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, days) }
        val endDate = String.format(
            "%04d-%02d-%02d",
            end.get(Calendar.YEAR),
            end.get(Calendar.MONTH) + 1,
            end.get(Calendar.DAY_OF_MONTH),
        )
        return api.get(
            "bill-occurrences",
            kotlinx.serialization.builtins.ListSerializer(Occurrence.serializer()),
            mapOf("end_date" to endDate, "limit" to "200"),
        )
    }

    suspend fun markBillPaid(occurrenceId: String): Occurrence = api.post(
        "bill-occurrences/$occurrenceId/mark-paid",
        EmptyBody(),
        EmptyBody.serializer(),
        Occurrence.serializer(),
    )

    suspend fun currentBudget(): BudgetSummary = api.get("budgets/current", BudgetSummary.serializer())

    suspend fun updateBudget(id: String, draft: BudgetDraft): BudgetSummary =
        api.patch("budgets/$id", draft.toJson(), BudgetSummary.serializer())

    suspend fun allCategories(): List<Category> = api.get(
        "categories",
        kotlinx.serialization.builtins.ListSerializer(Category.serializer()),
        mapOf("include_archived" to "true"),
    )

    suspend fun createCategory(name: String, color: String): Category = api.post(
        "categories",
        buildJsonObject {
            put("name", name.trim())
            put("color", color)
            put("kind", "expense")
        },
        JsonObject.serializer(),
        Category.serializer(),
    )

    suspend fun archiveCategory(id: String): Category =
        api.post("categories/$id/archive", EmptyBody(), EmptyBody.serializer(), Category.serializer())

    suspend fun deleteCategory(id: String) {
        api.delete("categories/$id")
    }

    suspend fun merchantAliases(): List<MerchantAlias> = api.get(
        "merchant-aliases",
        kotlinx.serialization.builtins.ListSerializer(MerchantAlias.serializer()),
    )

    suspend fun createAlias(alias: String, canonicalMerchant: String): MerchantAlias = api.post(
        "merchant-aliases",
        buildJsonObject {
            put("alias", alias.trim())
            put("canonical_merchant", canonicalMerchant.trim())
        },
        JsonObject.serializer(),
        MerchantAlias.serializer(),
    )

    suspend fun deleteAlias(id: String) {
        api.delete("merchant-aliases/$id")
    }

    /** The complete account export, as the server rendered it. */
    suspend fun exportJson(): String = api.getRaw("account/export")

    suspend fun deleteAccount(password: String, confirm: String) {
        api.postNoContent(
            "account/delete",
            buildJsonObject {
                put("password", password)
                put("confirm", confirm)
            }.toString(),
        )
    }

    suspend fun shoppingCheck(storeName: String, categoryId: String, amount: String?): ShoppingResult =
        api.post(
            "shopping/check",
            ShoppingRequest(storeName.trim().ifEmpty { "Store" }, categoryId, amount),
            ShoppingRequest.serializer(),
            ShoppingResult.serializer(),
        )

    // ---------------------------------------------------------------- Phase 4
    suspend fun loans(): LoanSummary = api.get("loans", LoanSummary.serializer())

    suspend fun createLoan(body: JsonObject): Loan =
        api.postJson("loans", body, Loan.serializer())

    suspend fun updateLoan(id: String, body: JsonObject): Loan =
        api.patch("loans/$id", body, Loan.serializer())

    suspend fun deleteLoan(id: String) {
        api.delete("loans/$id")
    }

    suspend fun addLoanPayment(loanId: String, body: JsonObject): LoanPayment =
        api.postJson("loans/$loanId/payments", body, LoanPayment.serializer())

    suspend fun loanPayments(loanId: String): List<LoanPayment> = api.get(
        "loans/$loanId/payments",
        kotlinx.serialization.builtins.ListSerializer(LoanPayment.serializer()),
    )

    suspend fun loanSuggestions(loanId: String): LoanPaymentSuggestions =
        api.get("loans/$loanId/suggestions", LoanPaymentSuggestions.serializer())

    /** A suggested repayment the user judges to be a real one. */
    suspend fun confirmLoanPayment(loanId: String, paymentId: String): LoanPayment =
        api.postJson(
            "loans/$loanId/payments/$paymentId/confirm",
            buildJsonObject { },
            LoanPayment.serializer(),
        )

    /** "That is not this loan's repayment" — the payment stays out of the balance. */
    suspend fun rejectLoanPayment(loanId: String, paymentId: String): LoanPayment =
        api.postJson(
            "loans/$loanId/payments/$paymentId/reject",
            buildJsonObject { },
            LoanPayment.serializer(),
        )

    suspend fun acceptLoanSuggestion(loanId: String, transactionId: String): LoanPayment =
        api.postJson(
            "loans/$loanId/suggestions/$transactionId",
            buildJsonObject { put("confirm", true) },
            LoanPayment.serializer(),
        )

    suspend fun savings(): SavingsSummary = api.get("savings", SavingsSummary.serializer())

    suspend fun createSavingsGoal(body: JsonObject): SavingsGoal =
        api.postJson("savings", body, SavingsGoal.serializer())

    suspend fun updateSavingsGoal(id: String, body: JsonObject): SavingsGoal =
        api.patch("savings/$id", body, SavingsGoal.serializer())

    suspend fun deleteSavingsGoal(id: String) {
        api.delete("savings/$id")
    }

    suspend fun contributeToGoal(id: String, amount: String, on: String?): SavingsGoal =
        api.postJson(
            "savings/$id/contributions",
            buildJsonObject {
                put("amount", amount)
                if (on != null) put("contributed_on", on)
            },
            SavingsGoal.serializer(),
        )

    suspend fun obligations(): Obligations = api.get("obligations", Obligations.serializer())

    // ------------------------------------------------- location-aware shopping
    suspend fun locationSettings(): LocationSettings =
        api.get("shopping/location-settings", LocationSettings.serializer())

    suspend fun updateLocationSettings(body: JsonObject): LocationSettings =
        api.patch("shopping/location-settings", body, LocationSettings.serializer())

    suspend fun trackedLocations(): List<TrackedLocation> = api.get(
        "shopping/locations",
        kotlinx.serialization.builtins.ListSerializer(TrackedLocation.serializer()),
    )

    suspend fun createLocation(body: JsonObject): TrackedLocation =
        api.postJson("shopping/locations", body, TrackedLocation.serializer())

    /** Adds a detected place to the tracked list, keeping the detection's own fix. */
    suspend fun createLocationFromVisit(visitId: String, body: JsonObject): TrackedLocation =
        api.postJson("shopping/locations/from-visit/$visitId", body, TrackedLocation.serializer())

    suspend fun updateLocation(id: String, body: JsonObject): TrackedLocation =
        api.patch("shopping/locations/$id", body, TrackedLocation.serializer())

    suspend fun deleteLocation(id: String) {
        api.delete("shopping/locations/$id")
    }

    suspend fun shoppingVisits(): ShoppingVisits =
        api.get("shopping/visits", ShoppingVisits.serializer())

    /** Geofence entry: only the identifier is sent, never a coordinate. */
    suspend fun recordArrival(locationId: String): VisitRecordResult =
        api.postJson("shopping/locations/$locationId/arrive", buildJsonObject { }, VisitRecordResult.serializer())

    /** A single detected fix, used by low-power discovery. */
    suspend fun detectVisit(body: JsonObject): VisitRecordResult =
        api.postJson("shopping/visits/detect", body, VisitRecordResult.serializer())

    suspend fun ignoreVisit(id: String) {
        api.postNoContent("shopping/visits/$id/ignore")
    }

    suspend fun deleteVisit(id: String) {
        api.delete("shopping/visits/$id")
    }

    suspend fun clearVisits() {
        // The server deletes every visit and keeps the tracked places.
        api.delete("shopping/visits")
    }

    /**
     * Asks a server what it is, before it is selected. Never authenticates, so the
     * password and session of the currently configured server stay with it.
     */
    suspend fun serverInfo(apiBaseUrl: String): ServerInfo {
        val base = ServerUrl.apiBaseFromStored(apiBaseUrl)
        return api.getAnonymous("${base}server/info", ServerInfo.serializer())
    }

    suspend fun saveBaseUrl(value: String) {
        val normalized = if (value.endsWith("/")) value else "$value/"
        session.saveBaseUrl(normalized)
    }

    suspend fun saveTheme(value: String) = session.saveTheme(value)

    suspend fun signOut() {
        session.clearToken()
    }
}

@kotlinx.serialization.Serializable
data class EmptyBody(val confirm: Boolean = true)

@kotlinx.serialization.Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    val display_name: String,
    val timezone: String,
    val currency: String = "USD",
)
