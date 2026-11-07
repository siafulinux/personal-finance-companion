package com.pfc.companion.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores API bearer tokens encrypted with an AES-256-GCM key that never leaves
 * the Android Keystore.
 *
 * The token book is keyed by server address (see [TokenBook]) so each self-hosted
 * server keeps its own session: switching servers neither forwards the old token
 * to the new address nor forces a fresh sign-in when the user switches back.
 *
 * Only ciphertext is written to app-private SharedPreferences. If the key is
 * invalidated (for example the user resets the device lock), [read] returns null
 * and the blob is dropped, which degrades to "signed out" rather than crashing.
 */
class SecureTokenStore(context: Context) {
    private val prefs =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /** Returns the token stored for [baseUrl], if any. */
    fun read(baseUrl: String): String? = readBook()[TokenBook.key(baseUrl)]

    /** True when at least one server still has a stored token. */
    fun hasAny(): Boolean = readBook().isNotEmpty()

    fun write(baseUrl: String, value: String) {
        val tokens = readBook().toMutableMap()
        tokens[TokenBook.key(baseUrl)] = value
        writeBook(tokens)
    }

    fun clear(baseUrl: String) {
        val tokens = readBook().toMutableMap()
        if (tokens.remove(TokenBook.key(baseUrl)) != null) writeBook(tokens)
    }

    fun clearAll() = prefs.edit().remove(KEY_TOKEN).commit()

    private fun readBook(): Map<String, String> {
        val stored = prefs.getString(KEY_TOKEN, null) ?: return emptyMap()
        val plainText = decrypt(stored) ?: return emptyMap()
        // A pre-0.3 build wrote a single bare token here. It has no server attached,
        // so [migrateLegacy] adopts it for the address that build was using.
        if (!plainText.trimStart().startsWith("{")) return emptyMap()
        return TokenBook.decode(plainText)
    }

    private fun writeBook(tokens: Map<String, String>) {
        if (tokens.isEmpty()) {
            prefs.edit().remove(KEY_TOKEN).commit()
            return
        }
        val blob = encrypt(TokenBook.encode(tokens)) ?: return
        // commit(), not apply(): the caller reads the book straight back, and a
        // token that appears to vanish after sign-in would be a confusing bug.
        prefs.edit().putString(KEY_TOKEN, blob).commit()
    }

    /** Adopts a bare token written by a pre-0.3 build for [baseUrl]. */
    fun migrateLegacy(baseUrl: String) {
        val stored = prefs.getString(KEY_TOKEN, null) ?: return
        val plainText = decrypt(stored) ?: return
        if (plainText.trimStart().startsWith("{")) return
        val token = plainText.trim()
        if (token.isEmpty()) {
            prefs.edit().remove(KEY_TOKEN).commit()
            return
        }
        write(baseUrl, token)
    }

    private fun encrypt(value: String): String? = try {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val cipherText = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        Base64.encodeToString(cipher.iv, Base64.NO_WRAP) +
            SEPARATOR +
            Base64.encodeToString(cipherText, Base64.NO_WRAP)
    } catch (_: Exception) {
        null
    }

    private fun decrypt(stored: String): String? = try {
        val parts = stored.split(SEPARATOR)
        if (parts.size != 2) {
            clearAll()
            null
        } else {
            val iv = Base64.decode(parts[0], Base64.NO_WRAP)
            val cipherText = Base64.decode(parts[1], Base64.NO_WRAP)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(TAG_BITS, iv))
            String(cipher.doFinal(cipherText), Charsets.UTF_8)
        }
    } catch (_: Exception) {
        // Key invalidated or blob corrupted: forget it and require sign-in.
        clearAll()
        null
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                // No user-authentication requirement: the app must refresh data
                // in the background without prompting for a fingerprint.
                .setUserAuthenticationRequired(false)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "pfc_session_token_key"
        const val PREFS_NAME = "companion_session_secure"
        const val KEY_TOKEN = "access_token_enc"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val TAG_BITS = 128
        const val SEPARATOR = ":"
    }
}
