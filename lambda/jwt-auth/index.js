import jwt from "jsonwebtoken";
import jwksClient from "jwks-rsa";

// JWKS endpoint for your Supabase project
const SUPABASE_URL = "https://xzhnbiqcobpzuggsomdi.supabase.co";

// Create JWKS client
const client = jwksClient({
  jwksUri: `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`,
  cache: true,
  cacheMaxAge: 600000, // Cache keys for 10 minutes
});

// Function to get signing key
function getKey(header, callback) {
  client.getSigningKey(header.kid, (err, key) => {
    if (err) {
      callback(err);
      return;
    }
    const signingKey = key.publicKey || key.rsaPublicKey;
    callback(null, signingKey);
  });
}

export const handler = async (event, context) => {
  try {
    console.log("Authorizer invoked with event:", JSON.stringify(event));

    // For TOKEN type authorizer, token is in event.authorizationToken
    const token = event.authorizationToken;

    if (!token) {
      console.error("Authorization failed: No token provided");
      throw new Error("Unauthorized"); // TOKEN type requires throwing error to deny
    }

    // Remove 'Bearer ' prefix if present
    const cleanToken = token.replace(/^Bearer\s+/i, "");

    // Verify token with JWKS (using callback-based verify)
    return new Promise((resolve, reject) => {
      jwt.verify(
        cleanToken,
        getKey,
        {
          algorithms: ["ES256", "HS256"], // Support both new and legacy keys
        },
        (err, decoded) => {
          if (err) {
            console.error("Token verification failed:", err.message);
            reject(new Error("Unauthorized"));
            return;
          }

          console.log(
            "Token verified successfully for user:",
            decoded.sub || decoded.email
          );

          // Supabase uses 'sub' field for user ID
          const policy = generatePolicy(
            String(decoded.sub || decoded.email || "user"),
            "Allow",
            event.methodArn,
            {
              userId: String(decoded.sub || ""),
              email: String(decoded.email || ""),
              role: String(decoded.role || ""),
            }
          );

          resolve(policy);
        }
      );
    });
  } catch (error) {
    console.error("Authorizer error:", error.message || error);
    throw new Error("Unauthorized"); // Client will see generic 401/403
  }
};

function generatePolicy(principalId, effect, resource, context = {}) {
  const authResponse = {
    principalId: principalId,
  };

  if (effect && resource) {
    authResponse.policyDocument = {
      Version: "2012-10-17",
      Statement: [
        {
          Action: "execute-api:Invoke",
          Effect: effect,
          Resource: resource,
        },
      ],
    };
  }

  // Add context (optional user data passed to backend)
  if (Object.keys(context).length > 0) {
    authResponse.context = context;
  }

  return authResponse;
}
