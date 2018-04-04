import numpy as np
import cvxopt.solvers
import logging
from kernel import Kernel
from Vmatrix import Vmatrix

MIN_SUPPORT_VECTOR_MULTIPLIER = 1e-7


class SVMTrainer(object):
    def __init__(self, kernel, c):
        self._kernel = kernel
        self._c = c

    def train(self, X, y, mode):
        """Given the training features X with labels y, returns a SVM
        predictor representing the trained SVM.
        """
        #mode = 1
        lagrange_multipliers = self._compute_multipliers(X, y,mode)
        return self._construct_predictor(X, y, lagrange_multipliers)

    def _gram_matrix(self, X):
        n_samples, n_features = X.shape
        K = np.zeros((n_samples, n_samples))
        # TODO(tulloch) - vectorize
        for i, x_i in enumerate(X):
            for j, x_j in enumerate(X):
                K[i, j] = self._kernel(x_i, x_j)
        return K

    def _construct_predictor(self, X, y, lagrange_multipliers):
        support_vector_indices = \
            lagrange_multipliers > MIN_SUPPORT_VECTOR_MULTIPLIER

        support_multipliers = lagrange_multipliers[support_vector_indices]
        support_vectors = X[support_vector_indices]
        support_vector_labels = y[support_vector_indices]

        # http://www.cs.cmu.edu/~guestrin/Class/10701-S07/Slides/kernels.pdf
        # bias = y_k - \sum z_i y_i  K(x_k, x_i)
        # Thus we can just predict an example with bias of zero, and
        # compute error.
        bias = np.mean(
            [y_k - SVMPredictor(
                kernel=self._kernel,
                bias=0.0,
                weights=support_multipliers,
                support_vectors=support_vectors,
                support_vector_labels=support_vector_labels).predict(x_k)
             for (y_k, x_k) in zip(support_vector_labels, support_vectors)])

        return SVMPredictor(
            kernel=self._kernel,
            bias=bias,
            weights=support_multipliers,
            support_vectors=support_vectors,
            support_vector_labels=support_vector_labels)

    def _compute_multipliers(self, X, y, mode):
        n_samples, n_features = X.shape

        K = self._gram_matrix(X)
        # Solves
        # min 1/2 x^T P x + q^T x
        # s.t.
        #  Gx \coneleq h
        #  Ax = b
        if mode == 1:
            P = cvxopt.matrix(np.outer(y, y) * K)
            q = cvxopt.matrix(-1 * np.ones(n_samples))

        # -a_i \leq 0
        # TODO(tulloch) - modify G, h so that we have a soft-margin L1 classifier
            G_std = cvxopt.matrix(np.diag(np.ones(n_samples) * -1))
            h_std = cvxopt.matrix(np.zeros(n_samples))

        # a_i \leq c
            G_slack = cvxopt.matrix(np.diag(np.ones(n_samples)))
            h_slack = cvxopt.matrix(np.ones(n_samples) * self._c)

            G = cvxopt.matrix(np.vstack((G_std, G_slack)))
            h = cvxopt.matrix(np.vstack((h_std, h_slack)))

            A = cvxopt.matrix(y.astype('d'), (1, n_samples))
            b = cvxopt.matrix(0.0)
        else:
            if mode == 2:
                P = cvxopt.matrix(np.outer(y, y) * K) + cvxopt.matrix(np.diag(np.ones(n_samples)*(1/(4*self._c))))
                q = cvxopt.matrix(-1 * np.ones(n_samples))

                # -a_i \leq 0
                # TODO(tulloch) - modify G, h so that we have a soft-margin L2 classifier
                G_std = cvxopt.matrix(np.diag(np.ones(n_samples) * -1))
                h_std = cvxopt.matrix(np.zeros(n_samples))

                # a_i \leq c
                #G_slack = cvxopt.matrix(np.diag(np.ones(n_samples)))
                #h_slack = cvxopt.matrix(np.ones(n_samples) * self._c)

                G = G_std
                h = h_std
                A = cvxopt.matrix(y.astype('d'), (1, n_samples))
                b = cvxopt.matrix(0.0)

            else:
                A = cvxopt.matrix(y.astype('d'), (1, n_samples))

                vc = Vmatrix(self._kernel,self._c)
                V, theta = vc.calculateEle(X,y,mode=3)
                V = V.T
                V = cvxopt.matrix(V)
                y = cvxopt.matrix(y)
                proY = 0.0
                for i in range(n_samples):
                    if y[i] == 1:
                        proY = proY+1

                P = (V+cvxopt.matrix(self._c*np.linalg.pinv(K).T))
                q = cvxopt.matrix(y.T*V(-1))# the 1 term componet??
                G_std = cvxopt.matrix(np.diag(np.ones(n_samples) * -1))
                h_std = cvxopt.matrix(np.zeros(n_samples))

                #a_i \leq c
                G_slack = cvxopt.matrix(np.diag(np.ones(n_samples)))
                h_slack = cvxopt.matrix(np.ones(n_samples) )

                G = cvxopt.matrix(np.vstack((G_std, G_slack)))
                h = cvxopt.matrix(np.vstack((h_std, h_slack)))

                b = cvxopt.matrix(proY)
        '''
        print(P.size)
        print(q.size)
        print(G.size)
        print(h.size)
        print(A.size)
        print(b.size)
        '''
        solution = cvxopt.solvers.qp(P, q, G, h, A, b)
        #print(solution)
        # Lagrange multipliers
        return np.ravel(solution['x'])


class SVMPredictor(object):
    def __init__(self,
                 kernel,
                 bias,
                 weights,
                 support_vectors,
                 support_vector_labels):
        self._kernel = kernel
        self._bias = bias
        self._weights = weights
        self._support_vectors = support_vectors
        self._support_vector_labels = support_vector_labels
        assert len(support_vectors) == len(support_vector_labels)
        assert len(weights) == len(support_vector_labels)
        logging.info("Bias: %s", self._bias)
        logging.info("Weights: %s", self._weights)
        logging.info("Support vectors: %s", self._support_vectors)
        logging.info("Support vector labels: %s", self._support_vector_labels)

    def predict(self, x):
        """
        Computes the SVM prediction on the given features x.
        """
        result = self._bias
        for z_i, x_i, y_i in zip(self._weights,
                                 self._support_vectors,
                                 self._support_vector_labels):
            result += z_i * y_i * self._kernel(x_i, x)
        return np.sign(result).item()

    def score(self, X, y):
        n_samples, n_features = X.shape

        result_predict = []
        error = 0
        for i in range(n_samples):
            point = X[i, :]
            point_predict = self.predict(point)
            result_predict.append(point_predict)
            if point_predict == y[i]:
                error = error+0

            else:
                error = error + 1

        error = float((n_samples-error)/n_samples)

        return error

