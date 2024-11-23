from lightphe.cryptosystems.Paillier import Paillier
from sympy import mod_inverse, gcd

class Ciphertext:
    def __init__(self, ciphertext: int, randomness: int):
        self.ciphertext = ciphertext
        self.randomness = randomness

    def __repr__(self):
        """
        Provide a string representation of the CipherData object for debugging.
        """
        return f"CipherData(ciphertext='{self.ciphertext}', randomness='{self.randomness}')"

    def display(self):
        """
        Display the ciphertext and randomness in a readable format.
        """
        print(f"Ciphertext: {self.ciphertext}")
        print(f"Randomness: {self.randomness}")


class Encryption:
    def __init__(self, public_key: int = None, private_key: int = None):
        """
        Initialize the Encryption class with a public and private key.
        
        :param public_key: The public key used for encryption.
        :param private_key: The private key used for decryption.
        """
        if public_key is None and private_key is None:
            self.paillier = Paillier()
        else:
            self.paillier = Paillier({private_key: private_key, public_key: public_key})
    
    def generate_random_key(self):
        """
        Generate a random key.
        """
        return self.paillier.generate_random_key()

    def encrypt(self, plaintext: int, rand: int):
        """
        Encrypt the given plaintext.

        :param plaintext: The plaintext integer to be encrypted.
        :return: Ciphertext object.
        """
        ct = self.paillier.encrypt(plaintext, rand)
        ciphertext_object = Ciphertext(ct, rand)
        return ciphertext_object

    def add(self, ct1, ct2):
        """
        Add two plaintext values securely with given randomness.

        :param pt1: The first plaintext.
        :param pt2: The second plaintext.
        :param randomness: Randomness or nonce.
        :return: Sum of the two plaintexts.
        """
        sum = self.paillier.add(ct1.ciphertext, ct2.ciphertext)
        combined_randomness = ct1.randomness*ct2.randomness
        ciphertext_object = Ciphertext(sum, combined_randomness)
        return ciphertext_object

    def obtain_ephermeral_key(self, ct):
        """
        Obtain an ephemeral key.
        """
        # Compute g^λ mod n^2
        g_lambda_mod_n_squared = pow((self.paillier.plaintext_modulo)+1, self.paillier.keys["private_key"]["phi"], self.paillier.ciphertext_modulo)
        
        # Compute L(g^λ mod n^2)
        g_lambda_L = (g_lambda_mod_n_squared - 1) // self.paillier.plaintext_modulo

        # Compute c^λ mod n^2
        c_lambda_mod_n_squared = pow(ct.ciphertext, self.paillier.keys["private_key"]["phi"], self.paillier.ciphertext_modulo)

        # Compute L(c^λ mod n^2)
        c_lambda_L = (c_lambda_mod_n_squared - 1) // self.paillier.plaintext_modulo

        # Recover plaintext m
        m = (c_lambda_L * mod_inverse(g_lambda_L, self.paillier.plaintext_modulo)) % self.paillier.plaintext_modulo

        # Step 2: Recover r^n from c and m
        g_m_mod_n_squared = pow((self.paillier.plaintext_modulo)+1, m, self.paillier.ciphertext_modulo)  # g^m mod n^2
        g_m_inv_mod_n_squared = mod_inverse(g_m_mod_n_squared, self.paillier.ciphertext_modulo)  # (g^m)^-1 mod n^2
        r_n = (ct.ciphertext * g_m_inv_mod_n_squared) % self.paillier.ciphertext_modulo  # r^n mod n^2

        # Step 3: Recover r (n-th root of r^n modulo n)
        for r in range(1, self.paillier.plaintext_modulo):  # Brute force over possible values of r
            if pow(r, self.paillier.plaintext_modulo, self.paillier.ciphertext_modulo) == r_n:
                return r

        raise ValueError("Failed to recover random factor r.")
    
    def decrypt(self, ct):
        """
        Decrypt the given ciphertext.

        :param ciphertext: The ciphertext to be decrypted.
        :return: The plaintext.
        """
        plaintext = self.paillier.decrypt(ct.ciphertext)
        return plaintext

    def serialize(self, ciphertext):
        """
        Serialize the ciphertext into a serializable format.

        :param ciphertext: The ciphertext object to serialize.
        :return: Serialized output.
        """
        pass


testing = Encryption()

c1 = testing.encrypt(5, 2)
c2 = testing.encrypt(10, 3)

c3 = testing.add(c1, c2)

print(testing.decrypt(c3))
print(testing.obtain_ephermeral_key(c3))