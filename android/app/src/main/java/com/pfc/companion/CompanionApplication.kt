package com.pfc.companion

import android.app.Application
import com.pfc.companion.data.ApiClient
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.SessionStore

object ServiceLocator {
    lateinit var session: SessionStore
        private set
    lateinit var repository: FinanceRepository
        private set

    fun init(app: Application) {
        if (::repository.isInitialized) return
        session = SessionStore(app)
        repository = FinanceRepository(ApiClient(session), session)
    }
}

class CompanionApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        ServiceLocator.init(this)
    }
}
