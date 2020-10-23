import os
import json

from ..arithmetic import bn128_Field, bn128_FieldPolynomial, log2, mul_scalar, G1, G2, pairing, FQ, field_properties

class Groth:
    def __init__(self, circuit_path):

        with open(circuit_path) as json_file:
            self.circuit = json.load(json_file)

        num_vars = int(self.circuit["nVars"])

        self.setup = {
            "vk_proof" : {
                "protocol" : "groth",
                "nVars"    : int(self.circuit["nVars"]),
                "nPublic"  : int(self.circuit["nPubInputs"] + self.circuit["nOutputs"]),
                "domainBits" : 0,
                "domainSize" : 0,
                "polsA" : [dict() for x in range(num_vars)],
                "polsB" : [dict() for x in range(num_vars)],
                "polsC" : [dict() for x in range(num_vars)]
            },
            "vk_verifier": {
                "protocol" : "groth",
                "nPublic"  : int(self.circuit["nPubInputs"] + self.circuit["nOutputs"])
            },
            "toxic" : {}
        }
        total_domain = int(self.circuit["nConstraints"]) + int(self.circuit["nPubInputs"]) + int(self.circuit["nOutputs"])
        self.setup["vk_proof"]["domainBits"] = log2(total_domain) + 1
        self.setup["vk_proof"]["domainSize"] = 1 << self.setup["vk_proof"]["domainBits"]

        #TODO : need random function
        self.setup["toxic"]["t"] = FQ(5, field_properties["bn128"]["q"]) # bn128_Field

        self.PF = bn128_FieldPolynomial()


    def calc_polynomials(self):
        num_constraints = len(self.circuit["constraints"])
        # consts = self.circuit["constraints"]
        for c in range(num_constraints):
            A = self.circuit["constraints"][c][0]
            B = self.circuit["constraints"][c][1]
            C = self.circuit["constraints"][c][2]
            for s in A:
                self.setup["vk_proof"]["polsA"][int(s)][c] = FQ(int(A[s]), field_properties["bn128"]["q"]) if A[s] != None else None
            for s in B:
                self.setup["vk_proof"]["polsB"][int(s)][c] = FQ(int(B[s]), field_properties["bn128"]["q"]) if B[s] != None else None
            for s in C:
                self.setup["vk_proof"]["polsC"][int(s)][c] = FQ(int(C[s]), field_properties["bn128"]["q"]) if C[s] != None else None

        n_pub_plus_n_out = int(self.circuit["nPubInputs"]) + int(self.circuit["nOutputs"])
        for i in range(n_pub_plus_n_out+1):
            self.setup["vk_proof"]["polsA"][i][num_constraints+i] = FQ(1, field_properties["bn128"]["q"]) # bn128_Field

    def calc_values_at_T(self):
        domain_bits = self.setup["vk_proof"]["domainBits"]
        toxic_t = self.setup["toxic"]["t"]
        z_t = self.PF.compute_vanishing_polynomial(domain_bits, toxic_t)
        u = self.PF.evaluate_lagrange_polynomials(domain_bits, toxic_t)

        n_vars = int(self.circuit["nVars"])

        a_t = [FQ(0, field_properties["bn128"]["q"])]*n_vars
        b_t = [FQ(0, field_properties["bn128"]["q"])]*n_vars
        c_t = [FQ(0, field_properties["bn128"]["q"])]*n_vars

        for s in range(n_vars):
            A = self.setup["vk_proof"]["polsA"][s]
            B = self.setup["vk_proof"]["polsB"][s]
            C = self.setup["vk_proof"]["polsC"][s]
            if A != None:
                for c in A:
                    a_t[s] = a_t[s] + u[int(c)] * int(A[c])

            if B != None:
                for c in B:
                    b_t[s] = b_t[s] + u[int(c)] * int(B[c])

            if C != None:
                for c in C:
                    c_t[s] = c_t[s] + u[int(c)] * int(C[c])

        return [a_t, b_t, c_t, z_t]


    def calc_encrypted_values_at_T(self):
        num_vars = int(self.circuit["nVars"])
        n_pub_plus_n_out = int(self.circuit["nPubInputs"]) + int(self.circuit["nOutputs"]) + 1
        a_t, b_t, c_t, z_t = self.calc_values_at_T()
        vk_proof_A = [None]*num_vars
        vk_proof_B1 = [None]*num_vars
        vk_proof_B2 = [None]*num_vars
        vk_proof_C = [None]*num_vars
        vk_proof_IC = [None]*n_pub_plus_n_out

        kalfa = FQ(5, field_properties["bn128"]["q"]) #TODO : should turn into random
        kbeta = FQ(5, field_properties["bn128"]["q"]) #TODO : should turn into random
        kgamma = FQ(5, field_properties["bn128"]["q"]) #TODO : should turn into random
        kdelta = FQ(5, field_properties["bn128"]["q"]) #TODO : should turn into random

        inv_delta = 1 / kdelta
        inv_gamma = 1 / kgamma

        g1 = G1()
        g2 = G2()

        vk_proof_alfa_1 = mul_scalar(g1.g, kalfa).affine()
        vk_proof_beta_1 = mul_scalar(g1.g, kbeta).affine()
        vk_proof_delta_1 = mul_scalar(g1.g, kdelta).affine()

        vk_proof_beta_2 = mul_scalar(g2.g, kbeta).affine()
        vk_proof_delta_2 = mul_scalar(g2.g, kdelta).affine()

        vk_verifier_alfa_1 = mul_scalar(g1.g, kalfa).affine()

        vk_verifier_beta_2 = mul_scalar(g2.g, kbeta).affine()
        vk_verifier_gamma_2 = mul_scalar(g2.g, kgamma).affine()
        vk_verifier_delta_2 = mul_scalar(g2.g, kdelta).affine()

        vk_verifier_alfabeta_12 = pairing(vk_verifier_alfa_1, vk_verifier_beta_2)
        for i in range(num_vars):
            A = mul_scalar(g1.g, a_t[i])
            vk_proof_A[i] = A
            B1 = mul_scalar(g1.g, b_t[i])
            vk_proof_B1[i] = B1
            B2 = mul_scalar(g2.g, b_t[i])
            vk_proof_B2[i] = B2

        for i in range(self.setup["vk_proof"]["nPublic"] + 1):
            ps = ((a_t[i] * kbeta) + (b_t[i] * kalfa) + c_t[i]) * inv_gamma
            IC = mul_scalar(g1.g, ps)
            vk_proof_IC[i] = IC

        for i in range(self.setup["vk_proof"]["nPublic"] + 1, num_vars):
            ps = ((a_t[i] * kbeta) + (b_t[i] * kalfa) + c_t[i]) * inv_delta
            C = mul_scalar(g1.g, ps)
            vk_proof_C[i] = C
        maxH = self.setup["vk_proof"]["domainSize"] + 1
        hExps = [None] * maxH
        zod = inv_delta * z_t
        hExps[0] = mul_scalar(g1.g, zod)
        eT = toxic_t = self.setup["toxic"]["t"]
        for i in range(1, maxH):
            hExps[i] = mul_scalar(g1.g, eT * zod)
            eT = eT * toxic_t
        self.setup["vk_proof"]["hExps"] = hExps
        self.setup["vk_proof"].update({
            "hExps": hExps,
            "A": vk_proof_A,
            "B1": vk_proof_B1,
            "B2": vk_proof_B2,
            "C": vk_proof_C,
            "vk_alfa_1": vk_proof_alfa_1,
            "vk_beta_1": vk_proof_beta_1,
            "vk_delta_1": vk_proof_delta_1,
            "vk_beta_2": vk_proof_beta_2,
            "vk_delta_2": vk_proof_delta_2
            })
        self.setup["vk_verifier"].update({
            "IC": vk_proof_IC,
            "vk_alfabeta_12": vk_verifier_alfabeta_12,
            "vk_alfa_1": vk_verifier_alfa_1,
            "vk_beta_2": vk_verifier_beta_2,
            "vk_gamma_2": vk_verifier_gamma_2,
            "vk_delta_2": vk_verifier_delta_2
            })
        self.setup["toxic"].update({
            "t": toxic_t,
            "kalfa": kalfa,
            "kbeta": kbeta,
            "kgamma": kgamma,
            "kdelta": kdelta
            })
        A = self.setup["vk_proof"]["A"]
        self.setup["vk_proof"]["A"] = g1.multi_affine(A)
        B1 = self.setup["vk_proof"]["B1"]
        self.setup["vk_proof"]["B1"] = g1.multi_affine(B1)
        B2 = self.setup["vk_proof"]["B2"]
        self.setup["vk_proof"]["B2"] = g2.multi_affine(B2)
        C = self.setup["vk_proof"]["C"]
        self.setup["vk_proof"]["C"] = g1.multi_affine(C)
        hExps = self.setup["vk_proof"]["hExps"]
        self.setup["vk_proof"]["hExps"] = g1.multi_affine(hExps)
        IC = self.setup["vk_verifier"]["IC"]
        self.setup["vk_verifier"]["IC"] = g1.multi_affine(IC)

if __name__ == "__main__":
    gr = Groth(os.path.dirname(os.path.realpath(__file__)) + "/test.r1cs.json")
    gr.calc_polynomials()
    at_list = gr.calc_values_at_T()
    gr.calc_encrypted_values_at_T()