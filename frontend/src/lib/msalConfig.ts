/**
 * Microsoft Azure AD MSAL Configuration
 *
 * Configuration for authenticating users with Microsoft Azure Active Directory
 * using the Microsoft Authentication Library (MSAL).
 */
 
import { Configuration, LogLevel } from "@azure/msal-browser";
 
/**
 * Azure AD configuration
 */
export const AZURE_CONFIG = {
  clientId: import.meta.env.VITE_AZURE_CLIENT_ID || "",
  tenantId: import.meta.env.VITE_AZURE_TENANT_ID || "",
  redirectUri: window.location.origin, // Uses current origin (http://localhost:5173)
} as const;
 
/**
 * MSAL Configuration
 *
 * This configuration is used to initialize the PublicClientApplication
 * that handles all authentication flows.
 */
export const msalConfig: Configuration = {
  auth: {
    clientId: AZURE_CONFIG.clientId,
    authority: `https://login.microsoftonline.com/${AZURE_CONFIG.tenantId}`,
    redirectUri: AZURE_CONFIG.redirectUri,
    postLogoutRedirectUri: AZURE_CONFIG.redirectUri,
  },
  cache: {
    cacheLocation: "sessionStorage",
  },
  system: {
    loggerOptions: {
      loggerCallback: (level: LogLevel, message: string, containsPii: boolean) => {
        if (containsPii) return;
       
        switch (level) {
          case LogLevel.Error:
            console.error(message);
            break;
          case LogLevel.Info:
            console.info(message);
            break;
          case LogLevel.Verbose:
            console.debug(message);
            break;
          case LogLevel.Warning:
            console.warn(message);
            break;
        }
      },
      logLevel: LogLevel.Warning,
    },
  },
};
 
/**
 * Scopes for login request
 *
 * These are the permissions we request from the user during login.
 * Basic profile information is requested by default.
 */
export const loginRequest = {
  scopes: ["openid", "profile", "email", "User.Read"],
};
 
/**
 * Scopes for accessing our backend API
 *
 * Note: If you exposed an API in Azure AD App Registration,
 * you can request a token for it like:
 * scopes: ["api://YOUR_API_CLIENT_ID/access_as_user"]
 *
 * For now, we'll use the standard Microsoft Graph scopes.
 */
export const tokenRequest = {
  scopes: ["openid", "profile", "email"],
};
